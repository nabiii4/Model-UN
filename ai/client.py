"""Every AI call in the app goes through this file (BUILD_PROMPT.md section 9).

What it handles so the rest of the code doesn't have to:
- Mock mode (no key): returns realistic pretend answers from ai/mock.py.
- GPT-5-family rules: max_completion_tokens (never max_tokens), no temperature/top_p/etc.,
  reasoning_effort that is dropped automatically if the deployment rejects it.
- Structured JSON output (strict json_schema, falling back to json_object), validated with
  Pydantic, with one "repair" call if the JSON doesn't match.
- Failover: retry the primary once on 429/5xx/timeout, then use the backup resource.
- A daily call cap for the whole site, and health info for the admin page.
Secrets never leave this file: errors shown to people never include keys or endpoints.
"""
import base64
import io
import json
import logging
import re
import threading
import time
from datetime import date

import openai
from pydantic import ValidationError

from ai import delivery, mock
from ai import persona as P
from ai.schemas import Feedback, Hint, PersonaCore, PersonaDraft, RoundOpening, TrainerOutput, TurnReply, strict_schema
from logic import data

log = logging.getLogger("nightmare.ai")

RETRYABLE = {429, 500, 502, 503, 504}
BUDGETS = {"persona": 6000, "turn": 2500, "feedback": 4000, "trainer": 5000, "hint": 1200, "listening": 1200,
           "opening": 2500, "probe": 1000}
TIMEOUTS = {"turn": 25, "vision": 45, "persona_text": 45, "feedback": 40, "trainer": 45, "hint": 25,
            "opening": 25, "probe": 25, "tts": 20, "transcribe": 30, "image": 90}
FEATURES = ("chat", "vision", "transcribe", "tts", "image", "embeddings")
BUILT_FEATURES = {"chat", "vision"}  # Phase 2/3 turn on the rest
MAX_TRANSCRIPT_CHARS = 1200


# ------------------------------------------------------------------ errors people can see

class AIError(Exception):
    code = "ai_error"
    default_message = "The nightmare factory hiccuped. Try again — or start a Human Round."

    def __init__(self, message=None, detail=""):
        super().__init__(detail or message or self.default_message)
        self.user_message = message or self.default_message


class AIUnavailable(AIError):
    code = "ai_unavailable"
    default_message = ("Both nightmare factories are on break. Try again in a minute — "
                       "or start a Human Round. Humans never time out.")


class AICapReached(AIError):
    code = "ai_cap"
    default_message = ("The club used all of today's AI turns. Try again tomorrow — "
                       "or start a Human Round. Humans never time out.")


class AIContentFiltered(AIError):
    code = "ai_filtered"
    default_message = "Let's keep things friendly for everyone. Want to try something else?"


class AIBadOutput(AIError):
    code = "ai_bad_output"
    default_message = "The AI got its words tangled. Try again — or start a Human Round."


class _EmptyReply(Exception):
    pass


# ------------------------------------------------------------------ resources

class Resource:
    """One Azure OpenAI resource (primary or backup), or the OpenAI-compatible provider."""

    def __init__(self, name, endpoint, key):
        self.name = name
        self.endpoint = endpoint
        self.key = key
        self.healthy = True          # False after 401/403 (key rejected)
        self.unavailable = set()     # features that returned 404
        self.use_v1 = False          # switched to the newer /openai/v1/ API after 404s
        self.clients = {}


def _classify(exc):
    """-> (kind, retry_after_seconds). kind: retryable / auth / not_found / bad_request / other."""
    status = getattr(exc, "status_code", None)
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError, TimeoutError)):
        return "retryable", 1.0
    if status in RETRYABLE:
        retry_after = 1.0
        try:
            header = exc.response.headers.get("retry-after")
            if header:
                retry_after = float(header)
        except Exception:
            pass
        return "retryable", retry_after
    if status in (401, 403):
        return "auth", 0
    if status == 404:
        return "not_found", 0
    if status == 400:
        return "bad_request", 0
    return "other", 0


def _error_text(exc):
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if body:
        try:
            parts.append(json.dumps(body))
        except Exception:
            parts.append(str(body))
    return " ".join(parts).lower()


def _extract_json(text):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    return json.loads(text)


class AIClient:
    def __init__(self, cfg, sdk_factory=None, sleep=time.sleep, counter=None, cap_provider=None):
        self.cfg = cfg
        self.mock = cfg.mock
        self.sdk_factory = sdk_factory
        self.sleep = sleep
        self.counter = counter            # counter(key) bumps a daily counter (set by the app)
        self.cap_provider = cap_provider  # returns today's cap (from Admin settings)
        self.reasoning_ok = True
        self.strict_ok = True
        self._lock = threading.Lock()
        self._calls_day = None
        self._calls_today = 0
        self.last_probe = 0.0
        self.resources = []
        if cfg.ai_provider == "openai_compatible":
            self.resources.append(Resource("primary", cfg.openai_base_url, cfg.openai_api_key))
        else:
            self.resources.append(Resource("primary", cfg.azure_endpoint, cfg.azure_key))
            if cfg.backup_endpoint and cfg.backup_key:
                self.resources.append(Resource("backup", cfg.backup_endpoint, cfg.backup_key))
        self.health = {f: {r.name: {"status": "unknown", "last_check": None, "last_error": None}
                           for r in self.resources} for f in FEATURES}
        self.failovers_today = 0

    # -------------------------------------------------------------- SDK clients

    def _model_for(self, feature):
        cfg = self.cfg
        if cfg.ai_provider == "openai_compatible":
            return cfg.openai_vision_model if feature == "vision" else cfg.openai_chat_model
        return cfg.vision_deployment if feature == "vision" else cfg.deployment

    def _client(self, res, media=False):
        key = (media, res.use_v1)
        if key in res.clients:
            return res.clients[key]
        if self.sdk_factory:
            client = self.sdk_factory(res, media)
        elif self.cfg.ai_provider == "openai_compatible":
            client = openai.OpenAI(base_url=res.endpoint, api_key=res.key, max_retries=0)
        elif res.use_v1:
            client = openai.OpenAI(base_url=res.endpoint.rstrip("/") + "/openai/v1/", api_key=res.key, max_retries=0)
        else:
            client = openai.AzureOpenAI(azure_endpoint=res.endpoint, api_key=res.key, max_retries=0,
                                        api_version=self.cfg.media_api_version if media else self.cfg.api_version)
        res.clients[key] = client
        return client

    # -------------------------------------------------------------- bookkeeping

    def _count_call(self):
        """Enforce the whole-site daily cap. Raises AICapReached when it's used up."""
        with self._lock:
            today = date.today()
            if self._calls_day != today:
                self._calls_day = today
                self._calls_today = 0
                self.failovers_today = 0
            cap = self.cfg.daily_call_cap
            if self.cap_provider:
                try:
                    cap = int(self.cap_provider())
                except Exception:
                    pass
            if self._calls_today >= cap:
                raise AICapReached()
            self._calls_today += 1
        if self.counter:
            try:
                self.counter("ai_calls")
            except Exception:
                log.exception("Could not bump the ai_calls counter")

    def _safe_error(self, exc):
        """An error message that is OK to show admins: no keys, no endpoints, no deployment names."""
        text = f"{type(exc).__name__}: {getattr(exc, 'status_code', '') or ''} {str(exc)[:200]}"
        hidden = [r.key for r in self.resources] + [r.endpoint for r in self.resources]
        hidden += [self.cfg.deployment, self.cfg.vision_deployment, self.cfg.openai_chat_model or ""]
        for h in hidden:
            if h and len(h) >= 4:
                text = text.replace(h, "[hidden]")
        text = re.sub(r"https?://\S+", "[link hidden]", text)
        return text.strip()

    def _mark(self, feature, res, status, exc=None, message=None):
        entry = self.health.setdefault(feature, {}).setdefault(res.name, {})
        entry["status"] = status
        entry["last_check"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if exc is not None or message:
            entry["last_error"] = message or self._safe_error(exc)

    # -------------------------------------------------------------- failover loop

    def _with_failover(self, feature, fn):
        resources = [r for r in self.resources if r.healthy and feature not in r.unavailable]
        if not resources:
            raise AIUnavailable()
        for idx, res in enumerate(resources):
            tries = 2 if idx == 0 else 1
            for attempt in range(tries):
                try:
                    out = fn(res)
                    self._mark(feature, res, "ok")
                    return out
                except AIError:
                    raise
                except Exception as exc:  # noqa: BLE001 - every SDK error is sorted by _classify
                    kind, retry_after = _classify(exc)
                    if kind == "retryable":
                        self._mark(feature, res, "error", exc)
                        log.warning("AI %s on %s resource failed (%s); attempt %d", feature, res.name,
                                    type(exc).__name__, attempt + 1)
                        if attempt + 1 < tries:
                            self.sleep(min(max(retry_after, 0.0), 3.0))
                            continue
                        break
                    if kind == "auth":
                        res.healthy = False
                        self._mark(feature, res, "error", message="Key rejected — check the key in your settings.")
                        log.error("AI key rejected on the %s resource (401/403).", res.name)
                        break
                    if kind == "not_found":
                        if self.cfg.ai_provider == "azure" and not res.use_v1:
                            # Some resources only answer on the newer v1 API. Try it once.
                            res.use_v1 = True
                            try:
                                out = fn(res)
                                log.warning("Switched the %s resource to the Azure v1 API after a 404.", res.name)
                                self._mark(feature, res, "ok")
                                return out
                            except AIError:
                                raise
                            except Exception:  # noqa: BLE001
                                res.use_v1 = False
                        res.unavailable.add(feature)
                        var = "AZURE_OPENAI_VISION_DEPLOYMENT" if feature == "vision" else "AZURE_OPENAI_DEPLOYMENT"
                        self._mark(feature, res, "error", message=f"Not found (404): check {var} and the API version in your settings.")
                        break
                    if kind == "bad_request":
                        self._mark(feature, res, "error", exc)
                        raise AIError(detail=self._safe_error(exc))
                    self._mark(feature, res, "error", exc)
                    break
            if idx == 0 and len(resources) > 1:
                self.failovers_today += 1
                if self.counter:
                    try:
                        self.counter("failovers")
                    except Exception:
                        pass
                log.warning("Failing over to the backup AI resource for %s.", feature)
        raise AIUnavailable()

    # -------------------------------------------------------------- one chat completion

    def _attempt(self, res, feature, system, convo, schema_model, budget, timeout):
        """One call on one resource, adapting to what the deployment accepts."""
        client = self._client(res)
        doubled = False
        while True:
            mode = None
            if schema_model is not None:
                mode = "json_schema" if self.strict_ok else "json_object"
            sys_text = system
            response_format = None
            if mode == "json_schema":
                response_format = {"type": "json_schema", "json_schema": {
                    "name": schema_model.__name__, "schema": strict_schema(schema_model), "strict": True}}
            elif mode == "json_object":
                sys_text = system + "\n\nReturn only JSON matching this schema:\n" + json.dumps(strict_schema(schema_model))
                response_format = {"type": "json_object"}
            kwargs = {"model": self._model_for(feature),
                      "messages": [{"role": "system", "content": sys_text}] + convo,
                      "max_completion_tokens": budget,
                      "timeout": timeout}
            if response_format:
                kwargs["response_format"] = response_format
            if self.reasoning_ok and self.cfg.reasoning_effort:
                kwargs["reasoning_effort"] = self.cfg.reasoning_effort
            self._count_call()
            try:
                resp = client.chat.completions.create(**kwargs)
            except openai.BadRequestError as exc:
                text = _error_text(exc)
                if "reasoning_effort" in text and "reasoning_effort" in kwargs:
                    self.reasoning_ok = False
                    log.warning("Deployment rejected reasoning_effort; continuing without it.")
                    continue
                if mode == "json_schema" and any(w in text for w in ("response_format", "json_schema", "schema")):
                    self.strict_ok = False
                    log.warning("Deployment rejected strict json_schema; falling back to json_object.")
                    continue
                if "content_filter" in text or "responsibleaipolicyviolation" in text or "content management" in text:
                    raise AIContentFiltered()
                raise
            choice = resp.choices[0]
            content = (choice.message.content or "").strip()
            if not content:
                if choice.finish_reason == "length" and not doubled:
                    budget *= 2
                    doubled = True
                    continue
                if choice.finish_reason == "content_filter":
                    raise AIContentFiltered()
                raise AIBadOutput(detail=f"empty reply (finish_reason={choice.finish_reason})")
            return content

    def chat_json(self, *, feature, system, convo, schema_model, budget, timeout, post=None):
        """Ask for JSON, validate it, and make one repair call if it doesn't match."""
        if self.mock:
            raise RuntimeError("chat_json is not used in mock mode")

        def parse(text):
            obj = schema_model.model_validate(_extract_json(text))
            return post(obj) if post else obj

        text = self._with_failover(feature, lambda res: self._attempt(res, feature, system, convo, schema_model, budget, timeout))
        try:
            return parse(text)
        except (ValueError, ValidationError) as exc:
            log.warning("AI JSON didn't match %s; making one repair call.", schema_model.__name__)
            repair = P.load_prompt("repair")
            r_sys = P.fill(repair["system"], schema_json=json.dumps(strict_schema(schema_model)))
            r_user = P.fill(repair["user"], error=str(exc)[:300], last_output=text[:6000])
            text2 = self._with_failover(feature, lambda res: self._attempt(
                res, feature, r_sys, [{"role": "user", "content": r_user}], schema_model, budget, timeout))
            try:
                return parse(text2)
            except (ValueError, ValidationError) as exc2:
                raise AIBadOutput(detail=str(exc2)[:300])

    def _mock_pause(self, factor=1.0):
        if self.cfg.mock_delay:
            time.sleep(self.cfg.mock_delay * factor)

    # ================================================================ tasks

    def persona_from_image(self, image_bytes, answers):
        """-> (persona, safety, dropped). Raises AIError on failure."""
        if self.mock:
            self._mock_pause(2.5)
            return self._finish_draft(mock.persona_from_image(image_bytes, answers))
        sections = P.load_prompt("persona_from_image")
        values = dict(P.answers_text(answers), pack_name="Model UN", role_noun="delegate", **P.id_lists())
        b64 = base64.b64encode(image_bytes).decode("ascii")
        convo = [{"role": "user", "content": [
            {"type": "text", "text": P.fill(sections["user"], **values)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
        ]}]
        draft = self.chat_json(feature="vision", system=sections["system"], convo=convo, schema_model=PersonaDraft,
                               budget=BUDGETS["persona"], timeout=TIMEOUTS["vision"], post=self._finish_draft)
        return draft

    def persona_from_text(self, description, answers):
        if self.mock:
            self._mock_pause(1.5)
            return self._finish_draft(mock.persona_from_text(description, answers))
        system = P.load_prompt("persona_from_image")["system"]
        user = P.fill(P.load_prompt("persona_from_text")["user"], description=description.replace('"', "'"),
                      pack_name="Model UN", role_noun="delegate", **P.answers_text(answers), **P.id_lists())
        return self.chat_json(feature="chat", system=system, convo=[{"role": "user", "content": user}],
                              schema_model=PersonaDraft, budget=BUDGETS["persona"], timeout=TIMEOUTS["persona_text"],
                              post=self._finish_draft)

    @staticmethod
    def _finish_draft(draft):
        """Validate/clamp a PersonaDraft (dict or model) -> (persona, safety, dropped)."""
        raw = draft.model_dump() if hasattr(draft, "model_dump") else dict(draft)
        safety = dict(raw.pop("safety", None) or {"status": "ok", "renamed_from_real_person": False, "note": None})
        persona, dropped = P.normalize_persona(raw)
        return persona, safety, dropped

    def revise_persona(self, persona, instruction):
        """-> {"summary", "changes", "persona"} (not saved)."""
        if self.mock:
            self._mock_pause(1.0)
            out = mock.revise_persona(persona, instruction)
            new, _ = P.normalize_persona(out["persona"])
            return {"summary": out["summary"], "changes": out["changes"], "persona": new}
        sections = P.load_prompt("trainer")
        system = P.fill(sections["system"], persona_json=P.export_persona_json(persona),
                        instruction=instruction.replace('"', "'"), **P.id_lists())
        out = self.chat_json(feature="chat", system=system, convo=[{"role": "user", "content": sections["user"]}],
                             schema_model=TrainerOutput, budget=BUDGETS["trainer"], timeout=TIMEOUTS["trainer"])
        new, _ = P.normalize_persona(out.persona, keep_training=persona.get("training"))
        changes = [c.model_dump() for c in out.changes][:12]
        return {"summary": delivery.limit_words(out.summary, 30), "changes": changes, "persona": new}

    def round_opening(self, persona, ctx):
        if self.mock:
            self._mock_pause(0.6)
            return mock.round_opening(persona, ctx)
        fmt = data.format_info(ctx["format"])
        sections = P.load_prompt("round_opening")
        system = P.fill(sections["system"], name=persona["name"], delegate_country=ctx["their_country"],
                        committee=ctx["committee"], topic=ctx["topic"], persona_summary=P.persona_summary(persona),
                        format_name=fmt["name"], student_opens="yes" if fmt["who_starts"] == "student" else "no")
        user = P.fill(sections["user"], student_country=ctx["my_country"])
        out = self.chat_json(feature="chat", system=system, convo=[{"role": "user", "content": user}],
                             schema_model=RoundOpening, budget=BUDGETS["opening"], timeout=TIMEOUTS["opening"])
        res = out.model_dump()
        if fmt["who_starts"] == "student":
            res["opening"] = None
        elif res.get("opening"):
            res["opening"] = delivery.limit_words(res["opening"], 60).rstrip("…")
        else:
            res["opening"] = f"Delegate of {ctx['my_country']}, what is your plan on {ctx['topic'].lower()}?"
        res["pois"] = [delivery.limit_words(p, 12).rstrip("…") for p in res.get("pois", []) if p][:3]
        res["human_round_question"] = delivery.limit_words(res.get("human_round_question") or "", 18).rstrip("…")
        if ctx["format"] != "moderated_caucus":
            res["caucus_subtopic"] = None
        elif res.get("caucus_subtopic"):
            res["caucus_subtopic"] = delivery.limit_words(res["caucus_subtopic"], 8).rstrip("…")
        return res

    def debate_turn(self, persona, ctx, history, student_text, *, heat, turn_index, examples, switched,
                    turn_info, time_up=False):
        tactic_ids = {t["id"] for t in persona.get("tactics", [])}
        if self.mock:
            self._mock_pause(0.6)
            out = mock.debate_turn(persona, ctx, student_text, heat, turn_index, switched=switched, time_up=time_up)
        else:
            system = P.turn_system_prompt(persona, ctx, heat, examples, switched)
            convo = []
            for m in history:
                if m["role"] == "delegate":
                    convo.append({"role": "assistant", "content": m["text"][:MAX_TRANSCRIPT_CHARS]})
                elif m["role"] == "student":
                    convo.append({"role": "user", "content": m["text"][:MAX_TRANSCRIPT_CHARS]})
            convo.append({"role": "user", "content": P.turn_user_message(
                student_text=student_text[:MAX_TRANSCRIPT_CHARS], **turn_info)})
            model = self.chat_json(feature="chat", system=system, convo=convo, schema_model=TurnReply,
                                   budget=BUDGETS["turn"], timeout=TIMEOUTS["turn"])
            out = model.model_dump()
            if time_up and heat >= 4 and "time, delegate" not in out["reply"].lower():
                out["reply"] = "Time, delegate. " + out["reply"]
        out["reply"] = delivery.limit_words(re.sub(r"[*_#`]", "", out["reply"]), 90).strip() or "Go on, delegate."
        out["eyebrows"] = max(-2, min(2, int(out.get("eyebrows", 0))))
        out["suggest_heat"] = max(-1, min(1, int(out.get("suggest_heat", 0))))
        if out.get("tactic_used") not in tactic_ids:
            out["tactic_used"] = "none"
        return out

    def hint(self, ctx, delegate_text):
        if self.mock:
            self._mock_pause(0.4)
            return mock.hint(ctx, delegate_text)
        sections = P.load_prompt("hint")
        system = P.fill(sections["system"], topic=ctx["topic"], student_country=ctx["my_country"],
                        delegate_text=(delegate_text or "")[:MAX_TRANSCRIPT_CHARS].replace('"', "'"))
        out = self.chat_json(feature="chat", system=system, convo=[{"role": "user", "content": sections["user"]}],
                             schema_model=Hint, budget=BUDGETS["hint"], timeout=TIMEOUTS["hint"])
        return {"idea": delivery.limit_words(out.idea, 20).rstrip("…"), "ask_back": delivery.limit_words(out.ask_back, 15).rstrip("…")}

    def feedback(self, persona, ctx, transcript, *, final_heat, switched, delivery_stats=None, listening=None):
        if self.mock:
            self._mock_pause(1.0)
            raw = mock.feedback(persona, ctx, transcript, final_heat, switched, delivery_stats)
        else:
            sections = P.load_prompt("feedback")
            fmt = data.format_info(ctx["format"])
            lines = []
            for m in transcript:
                if m["role"] in ("student", "delegate"):
                    lines.append(f"{'S' if m['role'] == 'student' else 'D'}: {m['text'][:MAX_TRANSCRIPT_CHARS]}")
            system = P.fill(sections["system"], format_name=fmt["name"], topic=ctx["topic"],
                            student_country=ctx["my_country"], name=persona.get("name", ""), final_heat=final_heat,
                            delivery_json=json.dumps(delivery_stats or {}), listening_json=json.dumps(listening or []),
                            switched_sides="yes" if switched else "no", transcript="\n".join(lines))
            raw = self.chat_json(feature="chat", system=system, convo=[{"role": "user", "content": sections["user"]}],
                                 schema_model=Feedback, budget=BUDGETS["feedback"], timeout=TIMEOUTS["feedback"]).model_dump()
        return finish_feedback(raw, transcript, switched=switched, listening_used=bool(listening))

    # ================================================================ health

    def probe(self, features=("chat", "vision")):
        """Tiny real calls to see if chat and vision work. Never raises."""
        self.last_probe = time.time()
        if self.mock:
            return
        for feature in features:
            if feature not in BUILT_FEATURES:
                continue
            try:
                if feature == "vision":
                    from PIL import Image
                    buf = io.BytesIO()
                    Image.new("RGB", (16, 16), "white").save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    content = [{"type": "text", "text": "What color is this image? One word."},
                               {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}}]
                else:
                    content = "Reply with the single word OK."
                self._with_failover(feature, lambda res: self._attempt(
                    res, feature, "You are a health check. Answer in one word.",
                    [{"role": "user", "content": content}], None, BUDGETS["probe"], TIMEOUTS["probe"]))
            except Exception as exc:  # noqa: BLE001 - a probe must never crash the app
                log.warning("AI health probe for %s failed: %s", feature, type(exc).__name__)

    def probe_async(self, app, features=("chat", "vision")):
        if self.mock:
            return

        def run():
            with app.app_context():
                self.probe(features)
        threading.Thread(target=run, daemon=True, name="ai-probe").start()

    def maybe_probe(self, app):
        if not self.mock and time.time() - self.last_probe > 15 * 60:
            self.last_probe = time.time()
            self.probe_async(app)

    def feature_status(self, feature):
        if feature not in BUILT_FEATURES:
            return "off"
        if self.mock:
            return "ok"
        states = []
        for r in self.resources:
            if not r.healthy or feature in r.unavailable:
                states.append("error")
            else:
                states.append(self.health.get(feature, {}).get(r.name, {}).get("status", "unknown"))
        if any(s in ("ok", "unknown") for s in states):
            return "ok"
        return "error"

    def public_health(self):
        """For GET /api/health: no keys, endpoints, or deployment names."""
        backup = next((r for r in self.resources if r.name == "backup"), None)
        return {
            "mock": self.mock,
            "features": {f: self.feature_status(f) for f in FEATURES},
            "backup": {"configured": backup is not None,
                       "status": ("ok" if backup and backup.healthy else "error") if backup else "off"},
        }

    def admin_status(self):
        rows = []
        for f in FEATURES:
            for r in self.resources:
                h = self.health.get(f, {}).get(r.name, {})
                status = h.get("status", "unknown")
                if f not in BUILT_FEATURES:
                    status = "off (later phase)"
                elif not r.healthy:
                    status = "key rejected"
                elif f in r.unavailable:
                    status = "not found (404)"
                rows.append({"feature": f, "resource": r.name, "status": "mock" if self.mock and f in BUILT_FEATURES else status,
                             "last_check": h.get("last_check"), "last_error": h.get("last_error")})
        return {"mock": self.mock, "mock_reason": self.cfg.mock_reason, "rows": rows,
                "failovers_today": self.failovers_today, "calls_today": self._calls_today,
                "reasoning_effort_supported": self.reasoning_ok, "strict_schema_supported": self.strict_ok}


def finish_feedback(raw, transcript, *, switched, listening_used):
    """Clamp scores, and make sure the strength quote is really something the student said."""
    student_texts = [m["text"] for m in transcript if m["role"] == "student"]
    fb = dict(raw)
    # verify_quote returns the AI's quote if it's real, otherwise the closest real sentence.
    # Keeping only the first 25 words keeps it a word-for-word piece of what they said.
    quote = delivery.verify_quote(fb.get("strength_quote", ""), student_texts)
    fb["strength_quote"] = " ".join(quote.split()[:25])
    for key, n in (("strength_why", 25), ("fix_focus", 8), ("fix_how", 45), ("try_next_time", 20), ("encouragement", 25)):
        fb[key] = delivery.limit_words(fb.get(key) or "", n)
    scores = dict(fb.get("scores") or {})
    for key in ("clarity", "evidence", "answering", "diplomacy", "listening", "perspective"):
        s = scores.get(key)
        if s is None:
            scores[key] = None
            continue
        scores[key] = {"score": max(1, min(5, int(s.get("score", 3)))), "reason": delivery.limit_words(s.get("reason", ""), 15)}
    for key in ("clarity", "evidence", "answering", "diplomacy"):
        if scores.get(key) is None:
            scores[key] = {"score": 3, "reason": "A solid start."}
    if not listening_used:
        scores["listening"] = None
    if switched and scores.get("perspective") is None:
        scores["perspective"] = {"score": 4, "reason": "You argued the other side. That takes flexibility."}
    if not switched:
        scores["perspective"] = None
    fb["scores"] = scores
    return fb
