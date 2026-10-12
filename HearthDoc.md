# Hearth: Project Plan

Oct 11, 2026 · @Swastik

Hearth is a self-hosted MCP server plus a simulated voice assistant that turns one family request into a plan you preview, approve and undo. It targets the Alexa+ track with the Open Source mini-challenge, and must be submitted by Oct 23, 2026 12:00 PDT (12:30 AM IST on Oct 24).

## At a glance

A parent says "get us ready for Saturday's tournament." Hearth replies with one plan that covers calendar clashes, the weather, travel time and a packing list. Nothing is saved until the parent approves it, and any approved plan can be undone.

- **Who it is for:** parents and caregivers who coordinate a household's week.
- **The one demo scenario:** a child's Saturday tournament with a clashing dentist appointment, rain in the forecast and a long drive.
- **What makes it different:** an agent that previews, asks, then acts, and remembers preferences across sessions ("same as last time").
- **Branding:** the project is Hearth. Keep Amazon and Alexa logos and names out of the app and the video, because the rules bar third-party trademarks.

## Rules that shape the build

The hackathon accepts either a self-hosted MCP server or a simulated Alexa+ web app. Hearth builds both, so one demo passes either reading of the rules.

| Requirement | What the rules say | How Hearth meets it |
| --- | --- | --- |
| Alexa+ track | A working Agent Skill or a self-hosted MCP server on spec 2025-11-25 or later over Streamable HTTP; a simulated Alexa+ web app is also allowed | Real MCP server plus a web-based assistant simulator that calls it |
| Runtime use of the tech | The repo must import and call the track's technology, not just name it in the README | The simulator is an MCP client that calls the server's tools over HTTP |
| Demo video | Under 3 minutes, public on YouTube or Vimeo, in English, showing the project working; no third-party trademarks or copyrighted music | Scripted 2:50 screen recording with original or no music |
| Repository | Public with a visible open-source licence, or private and shared with the Amazon reviewers | Public repo with an MIT licence shown in the About section |
| Product feedback | Required for every tool, API or SDK used | Written as you build, using the template in this doc |
| Open Source mini-challenge | A new, additional open-source project or a contribution to a public repo, with the contribution URL, repo URL, GitHub username and a description | A small separate MIT library extracted from Hearth (see build plan) |
| Friction log | Optional; up to a 10% judging bonus | Kept from day one |
| Judging | Stage 1 pass/fail on fit and use of the required tech; Stage 2 scores four equal criteria: tech implementation, design, potential impact, quality of the idea | Each demo beat is tied to one criterion |

One ambiguity to settle: the rules say "new, additional" open-source project. Publishing a separate library is the safe reading, so plan for that rather than relying on Hearth's own repo counting.

## User journey

The demo follows one request from spoken words to an approved, undoable plan.

1. **Ask.** The parent says, "Get us ready for Saturday's tournament."
2. **Gather.** Hearth reads the family calendar, saved preferences, the weather forecast and the drive time to the venue.
3. **Preview.** A plan card appears with conflicts (a dentist visit overlapping the first match), a rain warning, a leave-by time and a packing and shopping list. Nothing is saved yet.
4. **Adjust and approve.** The parent says, "Move the dentist to Monday," the card updates, and they tap Approve.
5. **Commit and undo.** Hearth writes the events and list, shows exactly what changed, and keeps an Undo button.
6. **Remember.** Next session, "same as last time" reuses the saved snack list and arrival buffer.

## Architecture

&#91;embedded content: architecture · 3 layers, 1 approval path\]

The simulator's model chooses tools, the server reads and drafts freely, and the gate rejects any write that lacks the token only the plan card's Approve button creates.

## MCP tools

Read-only tools gather facts, draft tools build a plan, and only two tools change saved data. The model cannot approve its own plan: the approval token is minted by the Approve button in the plan card, and `commit_plan` rejects any call without it.

| Tool | What it does | Changes saved data? | Needs approval? |
| --- | --- | --- | --- |
| `get_context` | Returns the week's calendar items and saved preferences | No | No |
| `check_conflicts` | Finds overlapping events and tight gaps | No | No |
| `get_forecast` | Fetches the forecast for the venue and date from Open-Meteo | No | No |
| `estimate_travel` | Estimates drive time between two saved places using bundled coordinates | No | No |
| `propose_plan` | Builds a draft plan and returns the plan card | Draft only | No |
| `revise_plan` | Applies a spoken change to the draft | Draft only | No |
| `commit_plan` | Writes events and the list from an approved draft | Yes | Yes |
| `undo_plan` | Restores the state from before a committed plan | Yes | Yes |
| `remember_preference` | Saves a preference such as the snack list or arrival buffer | Yes | Yes |

Stretch tool: `simulate_checkout` turns the shopping list into a mock order. It never takes payment details and sits behind the same approval gate.

## Zero-cost stack

Everything runs on your Windows laptop. No cloud account, card or paid key is needed.

| Layer | Choice | Cost | Note |
| --- | --- | --- | --- |
| Language | Python 3 in a virtual environment | $0 | Windows installer available; check the SDK's minimum Python version |
| MCP server | Official `mcp` Python SDK over Streamable HTTP | $0 | Pin the version: the release notes suggest `mcp>=1.28,<2` to stay on v1, and v2 renames `FastMCP` to `MCPServer`. In your first hour, confirm which line negotiates 2025-11-25 |
| Web backend | FastAPI | $0 | Serves the simulator and its web page. Run the MCP server as its own process so the HTTP boundary is real; mounting it inside FastAPI also works (the standalone `fastmcp` package documents `mcp.http_app()` mounted with the outer app's lifespan) |
| Plan card | MCP App: the tool's `_meta.ui.resourceUri` points to a `ui://` resource served as `text/html;profile=mcp-app` | $0 | Plain Python on the server side; the card is hand-written HTML and JavaScript that speaks the spec's postMessage methods |
| Assistant simulator | FastAPI backend plus one web page | $0 | The page is its own host: an iframe plus handlers for the card's messages, because host support varies. Voice input where the browser supports it; typed input as the fallback |
| Planner agent | Strands Agents SDK with its Ollama provider | $0 | Local model; needs enough free RAM and tool-calling quality varies, so keep a rule-based planner as the fallback. Using Strands is also your route to the AWS Builder challenge without a card |
| Storage | `sqlite3` from the Python standard library | $0 | Calendar, plans, preferences and the undo ledger; nothing to compile on Windows |
| Weather | Open-Meteo forecast API | $0 | No key needed; confirm its terms for your use before submitting |
| Calendar | Local JSON file of sample family events | $0 | No third-party calendar API |
| Tests | pytest with the SDK's Python client | $0 | Assert the handshake and the approval gate; the MCP Inspector is optional and runs through npx, so it needs Node |
| Recording | OBS Studio, then YouTube upload | $0 | Public link required |
| Repo | GitHub public repo, MIT licence | $0 | Licence must show in the About section |

## Build plan

Features freeze on Oct 20. Submit on the evening of Oct 22 (IST) and keep Oct 23 as spare. The real deadline is 12:30 AM IST on Oct 24.

| Day (IST) | Goal | Done when |
| --- | --- | --- |
| Oct 12 | Public repo with MIT licence; Python MCP server skeleton over Streamable HTTP | A pytest using the SDK's Python client connects and the log shows protocol version 2025-11-25 or later; friction log started |
| Oct 13 | SQLite schema, sample family calendar, read-only tools | `get_context`, `check_conflicts`, `estimate_travel` and `get_forecast` pass tests |
| Oct 14 | `propose_plan` and `revise_plan` with a rule-based planner | The Saturday scenario yields a correct draft with the dentist conflict |
| Oct 15 | `commit_plan`, `undo_plan`, approval token and undo ledger | A commit without a token is rejected; undo restores the exact prior state |
| Oct 16 | Assistant simulator: FastAPI backend, chat page, live tool-call side panel | Typed request runs end to end |
| Oct 17 | Plan card as an MCP App served from Python, with Approve, Edit and Undo | Approve in the card mints the token and commits |
| Oct 18 | Strands agent on Ollama, voice input, `remember_preference` | "Same as last time" works in a fresh session |
| Oct 19 | Extract the separate open-source library; write the README | A new user can run Hearth from the README alone |
| Oct 20 | Feature freeze; full rehearsal; first demo recording | Recording is under 3 minutes |
| Oct 21 | Final recording and upload; finish product feedback and friction log | Public YouTube link works while logged out |
| Oct 22 | Submit on Devpost | Submission confirmation received |
| Oct 23 | Spare day | Only fixes, no features |

The simulator's planner uses the Strands Agents SDK from the start. If it slows you down by Oct 18, swap in a plain Ollama client and drop the AWS Builder entry.

## Three-minute demo script

Target 2:50. Judges are not required to watch past 3:00, so the best material goes first. Each beat is tied to a judging criterion.

| Time | Show | Criterion it earns |
| --- | --- | --- |
| 0:00-0:15 | The problem: a Saturday with a clashing appointment, rain and a long drive | Quality of the idea |
| 0:15-0:45 | The spoken request; the side panel streams real tool calls and shows the 2025-11-25 handshake line | Tech implementation |
| 0:45-1:25 | The plan card: conflict, rain warning, leave-by time and list, with the database visibly unchanged | Design |
| 1:25-1:55 | A spoken edit ("move the dentist to Monday"), then Approve | Design |
| 1:55-2:15 | The committed changes and one tap of Undo restoring the prior state | Tech implementation |
| 2:15-2:35 | A fresh session where "same as last time" reuses saved preferences | Potential impact |
| 2:35-2:50 | Close: real MCP server, runs fully offline, open-source library, repo link | Potential impact |

Recording rules:

- Show the app running, not slides.
- Keep Amazon and Alexa logos, names and copyrighted music out of the video.
- Narrate in English and upload as public on YouTube.
- Check the link while logged out of your own account.

## Submission checklist

Tick each item before you press Submit. Items come from the official rules.

- [ ] Registered on Devpost and saved a draft submission early
- [ ] Public GitHub repo with an MIT licence visible in the About section
- [ ] README with setup and run steps, tested on a clean checkout
- [ ] Code imports and calls the MCP SDK at runtime in both the server and the simulator client
- [ ] Server log shows protocol version 2025-11-25 or later
- [ ] Text description of what Hearth does and how it works
- [ ] Demo video under 3 minutes, public on YouTube, in English, with no third-party trademarks or copyrighted music
- [ ] Product feedback written for every tool used: what it was for, what worked, what needs work, onboarding, and whether you would build with it again
- [ ] Tracks and mini-challenges selected: Alexa+ and Open Source (add AWS Builder only if Strands is used and described in the feedback)
- [ ] Open Source fields filled: contribution URL, repo URL, GitHub username and a description
- [ ] Optional: friction log entries and feature requests added
- [ ] Submitted at least a day before the deadline

## Risks and fallbacks

The tools work without the model, so the two biggest unknowns (the local model and the plan card) both have a safe fallback.

| Risk | Why it matters | Fallback |
| --- | --- | --- |
| Server does not negotiate spec 2025-11-25 | The Alexa+ track requires that version or later | Pin the mcp package version, check the handshake on Oct 12, and try the other SDK line (v1 or v2) if it does not negotiate 2025-11-25 |
| Plan card will not render in your own host | The card carries the Design score | Render the same card as plain HTML in the simulator from the tool's structured output, and keep the `ui://` resource declared |
| Local model is too weak or too slow | Tool calling varies by model and by laptop | Use the rule-based planner; every tool already works without a model |
| Voice input is unreliable | A failed live demo costs points | Typed input as a fallback; record the take that works |
| Weather API unavailable or its terms do not fit | A broken call breaks the scenario | Bundle a sample forecast file and say so in the demo |
| Open Source challenge judged "not additional" | The rules say new, additional project | Publish a separate MIT library with its own tests and README |
| Reads as a basic MCP wrapper | The rubric lists that as the "obvious" Alexa+ entry | Lead with the approval gate, undo, cross-session memory and the plan card |
| Python dependency problems on Windows | Lost days early | Use a fresh virtual environment, pin versions in a lockfile and run the full test suite on Oct 12 |
| Scope creep (checkout, Strands, extra tools) | Unfinished polish loses to a smaller, finished demo | Freeze features on Oct 20; stretch items only after the core demo is recorded |

## Friction log and product feedback

Write an entry the moment something slows you down. Friction logs can earn up to a 10% judging bonus, and real, specific entries are what the reviewers want. Add rows as you go.

| Date | Task attempted | Steps taken | Expected | Actual | Severity | Workaround | Suggestion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| (example) Oct 12 | Connect the MCP Inspector to the server | Started the server, entered the URL | Handshake succeeds | (what really happened) | Low / Medium / High | (what you did) | (one concrete fix) |

Product feedback is required for every tool, API or SDK you use. Answer these five points for each one:

1. What did you use it for?
2. What worked well (setup, docs, testing, performance, reliability)?
3. What needs work (errors, unclear docs, missing features, workarounds)?
4. How was the first hour, from nothing to hello world?
5. Would you build with it again, yes or no, and why?

Optional feature requests take a description, why it matters to your project, and a priority of Critical, Important or Nice-to-have.

## Sources

Checked on Oct 11, 2026. Re-read the official rules before you submit, because they can be amended.

Pages opened in full:

- [Build, Ship, Shape: Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/)
- [Official rules](https://amazonappdev2026.devpost.com/rules)
- [Resources](https://amazonappdev2026.devpost.com/resources)
- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)

* [Python SDK v2.0.0 release notes](https://newreleases.io/project/github/modelcontextprotocol/python-sdk/release/v2.0.0): v1 is in maintenance; v2 renames FastMCP to MCPServer.
* [FastMCP ASGI deployment](https://gofastmcp.com/deployment/asgi): mounting an MCP app inside FastAPI.
* [MCP Apps specification](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx): tool metadata, the `ui://` resource, its MIME type and the view-host methods.

Seen only as search results, not opened in full:

- [MCP TypeScript SDK on npm (Socket)](https://socket.dev/npm/package/@modelcontextprotocol/sdk/overview/1.32.1): v1.x implements the spec up to 2025-11-25.
- [MCP TypeScript SDK 2.0 compatibility (Zuplo)](https://zuplo.com/learn/mcp/compatibility/clients/typescript-sdk): default protocol revision 2025-11-25.
- [Strands Agents with Ollama](https://strandsagents.com/latest/user-guide/concepts/model-providers/ollama): native support for local Ollama models.

Not verified: whether the Python SDK negotiates 2025-11-25 (the release notes I opened do not name it), Open-Meteo's terms, browser speech API support on your setup, and whether Alexa+ itself renders MCP Apps. Treat those as things to confirm during the build.
