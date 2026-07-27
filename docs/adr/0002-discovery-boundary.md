# ADR 0002: Isolate LLM discovery from lifecycle inference

**Status:** Accepted · **Date:** 2026-07-27

OpenRouter web search may suggest emerging technologies, but it does
not classify evidence, score phases, or publish technologies. Suggestions are
schema-validated, persisted with sources, and require an administrator to create a
draft followed by normal collection, validation, and activation.

This boundary limits hallucination impact and keeps published estimates
reproducible without an LLM. Revisit only if a versioned extraction evaluation set,
cost controls, and human-review policy demonstrate a measurable quality gain.
