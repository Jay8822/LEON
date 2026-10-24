# LEON: Assumptions list

An assumption is something that must be true for the design to work, that the design never checks. Found by red-teaming each component: how would I break it, and what was it relying on? First pass completed 22 October 2026; CHESTER section (A66–A73) added 24 October 2026. Not exhaustive; verification partners are expected to add more.

[key] marks the most important. "Answer" is the design response, where one exists. "Open" means not yet answered.

## GRACIE
- A1. Thresholds are set correctly for the real hardware. Open: needs hardware data.
- A2. Every reading is a sensible, physically possible number. Answer: the rule book defines normal; anything outside it is abnormal.
- A3. Sensors tell the truth. Answer: cross-referencing against other agents.
- A4. [key] A failed component fails obviously. The dangerous case is a sensor stuck at a normal-looking value. Partly answered by cross-referencing. Open.
- A5. All agents agree what time it is, so logs line up. Open: system-wide time sync.
- A6. Logging never fails. Open.
- A7. [key] Context from other agents is accurate; one wrong agent could switch off another's alarm. Answer: rule-book checks and questioning.
- A8. When EDEN confirms a fix, it is real. Answer: sign-off rules.

## EDEN
- A9. An agent's report doesn't contradict itself. Answer: a clash is itself a fault.
- A10. EDEN can tell when two reports are the same fault. Open.
- A11. The orchestrator's filtering holds under load. Answer: deep health sweep.
- A12. [key] The raising agent is working properly. Answer: loop detection; challenge mechanism.
- A13. A fault withdrawn as fixed really is fixed. Answer: EDEN confirms all fixes.
- A14. Every raised fault gets dealt with. Answer: timeout floor; light flags.
- A15. EDEN's copies of the rule books are up to date. Open.
- A16. [key] EDEN herself is right. Answer: agents can challenge EDEN.
- A17. The rule books themselves are correct. Answer: rule books are the most-updated part; partners and testing.

## Orchestrator
- A18. It keeps up at peak load and nothing drops out unseen. Open.
- A19. [key] A stream of small faults really is small faults. Answer: deep health sweep.
- A20. Major faults are rare enough for priority to mean something. Open.
- A21. Only genuine critical faults use the bypass, and the bypass note always arrives. Open.
- A22. The orchestrator is the only route to EDEN, apart from the official bypasses. Open.
- A23. Only legitimate sources can instruct it. Answer: same rules for everybody.
- A24. Its hardware gets stable power. Answer: always-on components get first claim on power.
- A25. [key] The orchestrator itself never fails. Answer: orchestrator-failure rule; heartbeat.

## ETHAN
- A26. He can tell a real spike from a jittery sensor, at millisecond speed. Open.
- A27. [key] LUNAE's instructions are right. Answer: questioning; speed matching.
- A28. A partial thruster failure is caught before it becomes a spin. Open.
- A29. Engines can be shut down mid-cruise safely and restart reliably. Open: hardware.
- A30. [key] A human is available when ETHAN needs one. Answer: no-human fallback; boom faults wait in safe mode.
- A31. Only sensible commands reach him. Answer: questioning.
- A32. A wobbling throttle is spotted as abnormal. Answer: rule book.
- A33. Fuel readings are accurate. Open.
- A34. [key] Pressure sensors are reliable enough to act on in milliseconds. Answer: possible boom means safe mode; false shutdowns accepted.

## LUNAE
- A35. [key] She locks onto the right stars. Answer: three-case position scan.
- A36. She knows when she's lost her bearings, and recalibrates fast. Open: the ship flies blind meanwhile.
- A37. She can tell whether a fault elsewhere came from her instruction. Open.
- A38. Holds and safe modes only happen for real reasons. Open.
- A39. [key] Holding at the current position is achievable; nothing stays still in space. Answer: safe mode stays near position without wasting fuel; Hold lasts per instruction.

## HALIA
- A40. Her limits are enforced from outside her. Answer: the SystemCoordinator is the gatekeeper.
- A41. She understands what the crew actually meant. Open.
- A42. The person instructing her is really crew or ground control. Answer: video and identity checks.
- A43. [key] What she says is accurate; AI can invent numbers. Answer: on-screen data comes straight from the agent.
- A44. [key] The bridge is her only way out; logs could be a back door. Answer: her system is completely separate.
- A45. Requests reach the right agent, and she notices a mismatched answer. Open.

## SystemCoordinator
- A46. It can tell a real request from a fake. Answer: both the crew's request and the rules must agree.
- A47. Two simultaneous requests can't both get through. Open: build detail.
- A48. The door always closes. Answer: stuck crossings are forced closed.
- A49. Every crossing goes through every check. Open: build detail.
- A50. [key] It has no AI in it, and HALIA can't influence it. Design principle.
- A51. [key] It fails shut. Answer: fail-shut rule.
- A52. [key] The green chirp means everything really is fine. Answer: heartbeat.

## Bus
- A53. [key] Messages arrive undamaged. Answer: received checked against sent.
- A54. Messages arrive in the order sent. Open.
- A55. Every message arrives within a known maximum time. Open.
- A56. Failing connections fail cleanly, not intermittently. Open.
- A57. [key] One broken wire doesn't take down the whole bus. Answer: separate physical bypass; safe mode.

## Environment
- A58. The environment stays within the ship's design limits. Answer: set per craft.
- A59. [key] Radiation affects only what agents measure, not the agents themselves. Answer: existing checks catch an agent behaving oddly; chip hardening is later hardware work.
- A60. The safety system always has power. Answer: power priority.
- A61. Environment assumptions are set per craft and mission, tested against best and worst cases.

## Humans
- A62. [key] What humans enter is correct; wrong-but-believable entries pass rule checks (e.g. the Mars Climate Orbiter units mix-up, 1999). Answer: units on every number; questioning.
- A63. A wrong human instruction gets questioned. Answer: yes, same as any agent.
- A64. [key] Humans respond and take notice; too many alerts get ignored. Answer: light flags keep minor items quiet.
- A65. The manual override is used sensibly. Answer: post-override rerun.

## CHESTER
- A66. [key] CHESTER's memory survives a restart. Answer: he logs as he goes, plus ghost memory (see SPEC).
- A67. When he comes back, he accounts for the time he was off. Answer: ghost memory and his own log let him pick up where he left off.
- A68. He keeps track of everything at peak, and never silently drops an item when full. Answer: storage-full rule (see SPEC).
- A69. [key] Agents act on what he tells them. Answer: if an agent ignores him, he notifies the orchestrator, which pings that agent to confirm it's active; a flag is added to CHESTER's log.
- A70. He tells the right agent; relies on the rule book's ownership map being correct. Open.
- A71. The message itself is right, with no mix-up between tracked items. Answer: everything and everybody is treated the same, so the receiving agent checks and questions his messages like any other.
- A72. His clock is right; every timer depends on it. Open: system-wide time sync, linked to A5.
- A73. [key] He can't be used as a back door: he sees everything, so his messages are information only, never instructions. Design principle.