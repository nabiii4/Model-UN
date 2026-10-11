<!-- Used once when the AI's JSON didn't match the schema. -->
=== system ===
Return only JSON matching this schema. No other text.
{schema_json}
=== user ===
Here is your last output. It did not match the schema ({error}). Fix it and return only the corrected JSON.
{last_output}
