"""LLM prompt'ları — versionable, testable.

Her prompt:
  - SYSTEM_PROMPT_VX (string)
  - render_user_payload(...) (input formatı)
  - parse_response(text) → struct (JSON parse + validation)
  - PROMPT_VERSION (semver-ish)
"""
