# Contributing

Thanks for your interest in improving the AEC Knowledge Graph. Contributions
of all kinds are welcome — bug reports, feature ideas, documentation fixes,
and code.

## Reporting an issue

Open a [GitHub issue](../../issues) and include:

- What you did, what you expected, and what happened instead.
- Your environment (OS, Python version, Neo4j version or Aura).
- Relevant logs or error messages.

For questions or ideas that aren't bugs, open an issue with the
`question` or `enhancement` label.

## Suggesting an improvement

Open an issue describing the improvement and the use case behind it before
writing code — this avoids wasted effort if the design needs discussion.

## Contributing code

1. Fork the repository and create a feature branch from `main`.
2. Set up a development environment:

   ```bash
   pip install -r requirements.txt
   pip install pytest
   cp .env.example .env   # fill in Neo4j + Gemini credentials
   ```

3. Make your changes. Match the existing code style (plain Python,
   type hints where they help, logging over prints).
4. Run the test suite:

   ```bash
   pytest
   ```

   Tests must pass without a database or API key — anything that needs
   Neo4j or Gemini belongs behind an env-gated integration test.
5. Open a pull request against `main` describing what changed and why.

## Scope notes

- The IFC layer of the graph is read-only by design; changes to ingestion
  should preserve that.
- The UCKS schema (`ucks_models.py`) is versioned (`ucks/0.1`) — breaking
  changes to it need a version bump and discussion first.

## Code of conduct

Be respectful and constructive. This is an academic open-source project;
assume good faith.
