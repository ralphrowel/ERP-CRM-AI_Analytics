# Visiq — Portfolio Showcase & Architecture Reference

Welcome to the documentation and media showcase directory for **Visiq: Autonomous AI Data Analyst Agent**. This folder contains presentation-ready technical documentation, architecture diagrams, sequence workflows, and engineering case studies tailored for web portfolios, technical blog posts, and engineering interviews.

---

## Media & Visual Artifacts

### 1. System Architecture Diagram
High-level component breakdown showing the Presentation layer, Enterprise Security Perimeter, Agent Coordinator with Tri-Modal Intent Routing, Dual-Engine Storage, and Cloud Production Infrastructure.

![Visiq Architecture Diagram](architecture_diagram.svg)

---

### 2. End-to-End Query Execution Pipeline
9-step sequence demonstrating how a natural-language question is checked against token quotas, routed to a deterministic sandbox, rendered into Plotly visualizations, and returned with token metrology.

![Visiq Workflow Pipeline](workflow_diagram.svg)

---

## Portfolio Quick Summary (Copy & Paste Ready)

> **Visiq** is a production-grade autonomous data analyst platform that transforms conversational questions into deterministic Python code execution, interactive Plotly visualizations, and actionable insights. Built with **FastAPI**, **React 18**, **Tailwind CSS v4**, **SQLAlchemy 2.0**, **Supabase Auth & Storage**, and deployed on **Railway & Vercel**, Visiq pairs ultra-fast LLM inference (Groq/Gemini) with the mathematical precision of a zero-hallucination Pandas sandbox. It features enterprise-grade security including path-containment guards, 5MB streaming request boundaries, Copy-on-Write dataset isolation, persistent cloud object storage, and atomic per-client daily token allowances.

### Key Highlights for Recruiters & Technical Evaluators
- **Explore as Guest (Instant Demo)**: One-click recruiter demo preloaded with an 8,807-title Netflix dataset, starter prompts, and instant chat view with zero signup friction.
- **Interactive Guided Product Tour**: Native onboarding tour spotlighting live dataset badges, spreadsheet mutator, chat canvas, and real-time visualization panels.
- **Hybrid Intent Routing**: Automatically classifies queries into `structured` (deterministic pandas execution), `rag` (semantic document retrieval), or `hybrid` (multi-step numerical + domain reasoning).
- **Mathematical Accuracy**: Prevents LLM numerical hallucinations by delegating calculations to a sandboxed Python execution engine rather than relying on generative predictions.
- **Copy-On-Write (COW) Multi-Tenancy**: Users can mutate shared datasets in-browser without corrupting baseline samples; mutations dynamically branch into private user storage vaults.
- **Dual-Engine Persistence & Cloud Storage**: Turnkey local SQLite fallback with seamless scaling to Supabase PostgreSQL, paired with Supabase Storage bucket persistence for uploaded datasets.
- **Enterprise Security & Token Quota Guard**: Enforces 50,000 daily token limits for authenticated users and a 10,000 token budget for guests, coupled with RS256 JWKS JWT authentication.
- **Production Cloud Deployment**: Fully automated CI/CD pipeline running the backend on Railway, the frontend on Vercel, and persistent state on Supabase.
- **Test-Driven Reliability**: Backed by **60 automated integration and security tests** validating every layer from directory traversal resistance to quota exhaustion.

---

## Detailed Case Study
For the complete technical write-up, see **[PORTFOLIO_CASE_STUDY.md](PORTFOLIO_CASE_STUDY.md)**, which includes:
- Problem statement & design motivations
- Detailed architectural breakdown & sequence diagrams
- In-depth security hardening specifications
- Live cloud deployment & container infrastructure (Railway + Vercel + Supabase)
- Comprehensive technology stack evaluation
- Schema definitions and API endpoint references
