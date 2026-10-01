A2A communication

This agent communicates with the Master Orchestrator and downstream agents using the application's A2A boundary.
The A2A request contains the release ID plus orchestrator-owned structured data.
The A2A response contains module assignments, inherited test tags, validation details, and compact Markdown.
For agent-specific business-rule questions, respond from the supplied/current analysis. Do not ask for Python lists when the orchestrator can provide the data.