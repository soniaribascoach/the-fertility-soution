def setup_tracing(endpoint: str = "", api_key: str = "") -> None:
    """
    Registers Arize Phoenix OTEL tracing and auto-instruments OpenAI calls.
    No-op if endpoint or api_key is not configured.
    """
    if not endpoint or not api_key:
        return

    try:
        from phoenix.otel import register
        from openinference.instrumentation.openai import OpenAIInstrumentor

        register(
            project_name="fertility-chatbot",
            endpoint=endpoint,
            headers={"api_key": api_key},
        )
        OpenAIInstrumentor().instrument()
    except ImportError:
        # Tracing packages not installed — silently skip
        pass
