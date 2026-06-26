"""
Local LLM Interface

Wraps llama-cpp-python to load a quantized GGUF model once and expose
a simple generate() function for the RAG pipeline.

Falls back to a template-based response generator when the LLM model
is not available (for demo/testing without a GPU-heavy model).
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.config import llm_cfg, get_path


_LLM_INSTANCE = None


# ── Prompt Templates ──

SYSTEM_PROMPT = """You are NetOps Co-Pilot, an AI assistant for network operations teams.
You help operators diagnose and remediate network issues using information from official runbooks and standard operating procedures (SOPs).

RULES:
1. ONLY use information from the provided runbook context to answer questions.
2. Always cite the source runbook ID (e.g., RB-101, RB-102) when providing recommendations.
3. If the runbook context does not contain relevant information, explicitly say: "This issue is not covered in the available runbooks. Please consult the network engineering team."
4. Be concise but thorough. Prioritize actionable steps.
5. When describing remediation steps, list them in order of urgency (immediate → short-term → preventive).
6. Include relevant CLI commands when available.
7. Always mention the escalation path if the issue cannot be resolved at the operator level."""


RAG_PROMPT_TEMPLATE = """Based on the following runbook context, answer the operator's question.

=== RUNBOOK CONTEXT ===
{context}
=== END CONTEXT ===

=== ALERT CONTEXT (if applicable) ===
{alert_context}
=== END ALERT CONTEXT ===

OPERATOR QUESTION: {question}

Provide a clear, actionable answer with runbook citations. If the context doesn't cover this issue, say so explicitly."""


class TemplateResponder:
    """
    Fallback responder that generates structured answers from retrieved
    runbook content without an actual LLM. Good enough for demo purposes
    when the model file isn't available.
    """

    def generate(self, prompt: str, context: str = "", **kwargs) -> str:
        """Generate a template-based response from context."""
        if not context or context.startswith("No relevant runbook"):
            return (
                "⚠️ This issue is not covered in the available runbooks. "
                "Please consult the Network Engineering team for guidance.\n\n"
                "**Recommended actions:**\n"
                "1. Collect device diagnostics (`show tech-support`)\n"
                "2. Document the symptoms and timeline\n"
                "3. Escalate to L3 Network Engineering"
            )

        # Parse out runbook sources from context
        import re
        sources = re.findall(r"\[Source \d+: (RB-\d+)(?:\s*—\s*([^\]|]+))?", context)

        # Build a structured response
        response_parts = ["**📋 Co-Pilot Analysis**\n"]

        # Extract sections from context
        sections = context.split("---")
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            # Find section headers
            source_match = re.search(r"\[Source \d+: (RB-\d+)(?:\s*—\s*([^\]|]+))?", section)
            if source_match:
                rb_id = source_match.group(1)
                section_name = source_match.group(2) or "General"
                response_parts.append(f"\n**Reference: {rb_id} — {section_name.strip()}**")

            # Extract numbered steps
            steps = re.findall(r"\d+\.\s\*\*(.+?)\*\*:?\s*(.+?)(?=\n\d+\.|\n\n|$)", section, re.DOTALL)
            if steps:
                for title, detail in steps[:4]:
                    detail_clean = detail.strip().split("\n")[0][:200]
                    response_parts.append(f"  - **{title.strip()}**: {detail_clean}")

            # Extract bullet points
            bullets = re.findall(r"[-•]\s(.+)", section)
            if bullets and not steps:
                for bullet in bullets[:5]:
                    response_parts.append(f"  - {bullet.strip()[:150]}")

        # Add citations
        if sources:
            response_parts.append("\n**📖 Sources:**")
            seen = set()
            for rb_id, section_name in sources:
                if rb_id not in seen:
                    response_parts.append(f"  - {rb_id}: {section_name.strip() if section_name else 'See runbook'}")
                    seen.add(rb_id)

        response_parts.append(
            "\n**⚠️ Escalation:** If the issue persists after following these steps, "
            "escalate per the runbook's escalation procedure."
        )

        return "\n".join(response_parts)


class LocalLLM:
    """Wrapper around llama-cpp-python for local LLM inference."""

    def __init__(self, model_path: str, **kwargs):
        from llama_cpp import Llama

        cfg = llm_cfg()
        self.llm = Llama(
            model_path=model_path,
            n_ctx=cfg.get("context_length", 4096),
            n_threads=cfg.get("n_threads", 4),
            verbose=False,
        )
        self.cfg = cfg

    def generate(self, prompt: str, context: str = "", **kwargs) -> str:
        """Generate a response using the local LLM."""
        full_prompt = RAG_PROMPT_TEMPLATE.format(
            context=context,
            alert_context=kwargs.get("alert_context", "None"),
            question=prompt,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt},
        ]

        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=self.cfg.get("max_tokens", 1024),
            temperature=self.cfg.get("temperature", 0.2),
            top_p=self.cfg.get("top_p", 0.9),
            repeat_penalty=self.cfg.get("repeat_penalty", 1.1),
        )

        return response["choices"][0]["message"]["content"]


def get_llm():
    """Get or create the LLM instance."""
    global _LLM_INSTANCE
    if _LLM_INSTANCE is not None:
        return _LLM_INSTANCE

    cfg = llm_cfg()
    model_path = get_path("paths.llm_model")

    if model_path.exists():
        try:
            _LLM_INSTANCE = LocalLLM(str(model_path))
            print(f"✅ Loaded local LLM from {model_path}")
        except Exception as e:
            print(f"⚠️  Failed to load LLM ({e}), using template responder")
            _LLM_INSTANCE = TemplateResponder()
    else:
        print(f"⚠️  LLM model not found at {model_path}, using template responder")
        _LLM_INSTANCE = TemplateResponder()

    return _LLM_INSTANCE


def generate_response(
    question: str,
    context: str = "",
    alert_context: str = "",
) -> Dict[str, Any]:
    """
    Generate a grounded response to an operator question.

    Args:
        question: the operator's question
        context: formatted runbook context from retriever
        alert_context: optional alert details for context

    Returns:
        Dict with answer, model_type, latency_ms
    """
    llm = get_llm()
    start = time.time()

    answer = llm.generate(
        prompt=question,
        context=context,
        alert_context=alert_context,
    )

    latency = (time.time() - start) * 1000

    return {
        "answer": answer,
        "model_type": "local_llm" if isinstance(llm, LocalLLM) else "template_responder",
        "latency_ms": round(latency, 1),
    }


if __name__ == "__main__":
    response = generate_response(
        question="How do I diagnose high CPU on a router?",
        context="[Source 1: RB-101 — Diagnosis Steps]\n1. **Identify the process consuming CPU**: Run `show processes cpu sorted`...",
    )
    print(f"Model: {response['model_type']}")
    print(f"Latency: {response['latency_ms']}ms")
    print(f"Answer:\n{response['answer']}")
