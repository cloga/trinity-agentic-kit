---
name: theme-driven-visual-design
description: Design and refine topic-specific visuals for narrated videos, explainers, or presentations. Use when planning scenes, diagrams, objects, charts, or motion, or when visuals feel like repetitive boxes or a generic template.
---

# Theme-Driven Visual Design

Turn the specific topic, argument, and narration into a visual explanation.
This is a provider-neutral design and review workflow, not a renderer or a
publication integration. Apply it whenever the task calls for visual planning
or refinement; do not wait for another reminder to avoid generic templates.

## Establish the brief and execution boundary

Read the supplied topic, audience, intended takeaway, narration, evidence,
output format, and any existing visual assets or project conventions. Reuse
these inputs rather than asking the user to repeat them. Identify missing
facts as gaps; do not invent facts, chart values, quotes, or source attribution.

Check which inspection, drawing, composition, rendering, and playback tools
are actually available. A renderer mentioned in prose is not proof that it is
installed, connected, or authorized. Use existing tools and reviewed assets
within the caller's permissions, provider restrictions, budget, and licenses.
Do not install dependencies, contact a provider, purchase assets, or create
external side effects merely because this Skill requests a preview.

When the complete workflow is already authorized, make ordinary design choices
and iterate autonomously within that authorization. Do not repeatedly request
approval for the same design package. A new expense, scope change, missing
permission, or required approval remains a real boundary. This Skill never
grants permission to publish, change schedules, access accounts, or bypass a
consumer's safety and quality gates.

## Design from meaning, not a reusable scene shell

Independently reason about each episode's topic meaning, knowledge mechanism,
argument, and narration before choosing its visuals. Do not replace that
reasoning with hardcoded topic-keyword-to-image or keyword-to-shot mappings,
fixed assembly rules, or a template that predetermines the scene sequence.
Existing coded primitives, asset libraries, and layout patterns may remain
optional materials selected for their explanatory fit; factual, accessibility,
and safety constraints still apply. The distinction is between reusable
building blocks and rules that make the creative decision instead of the agent.

1. State the single takeaway and the question or misconception the visuals
   should resolve. Break the narration into meaningful beats, not arbitrary
   equal-length slots.
2. For each beat, identify its role: comparison, accumulation, causal change,
   process, scale, uncertainty, or another relationship supported by the topic.
   Choose a visual mechanism that makes that relationship easier to understand.
3. Select concrete objects, a diagram, a chart, spatial relationships, or a
   restrained metaphor because they explain this beat. For example, a measured
   timeline can explain delayed effects; a flow can explain where resources
   move. Neither is a mandatory template for unrelated topics.
4. Specify what changes on screen and why it changes with the narration:
   objects entering or leaving, quantities accumulating, a link revealing a
   consequence, or a camera move revealing context. Motion must communicate,
   not merely decorate or keep the frame busy.
5. Match composition, typography, contrast, pacing, and information density to
   the audience and output size. Keep captions readable and clear of important
   objects; use consistent visual encodings for the same meaning.
6. Preserve a coherent style across scenes while varying the explanatory
   mechanism where the argument changes. Repetition is justified when it lets
   viewers compare the same variable, not merely because a template exists.

Do not substitute narration inside repeated fixed boxes, cards, or a single
stock layout for visual reasoning. Rectangles, grids, and repeated layouts
are acceptable when the actual relationship calls for them. Do not force
novelty at the expense of clarity, or imply causality with arrows when the
evidence establishes only association.

Keep factual charts traceable to supplied evidence, with appropriate units,
scale, and uncertainty. Clearly distinguish illustrative metaphors from
measurements; never fabricate numeric data to make a chart look complete.

## Make the plan executable

Produce a compact scene plan in the current task's expected format. For each
beat include:

- narration or its exact reference, takeaway, and supporting evidence;
- chosen objects or graphic, their relationship, and why this fits the topic;
- composition, labels, and intended changes or motion cues aligned to narration;
- available asset/tool dependencies and an observable acceptance criterion.

Use an existing project renderer when its supported primitives and input
contract can express the intended explanation. An existing general-purpose
renderer is not a prerequisite: if it only stitches static scenes or cannot
express the required motion, actively assess available drawing, composition,
and animation tools. Within existing permissions and cost limits, write or
combine topic-specific scenes, object transformations, and motion sequences
using those tools, then preview and inspect the result.

Do not silently remove meaningful motion or force the design into a static
template merely to fit an existing renderer. Report a concrete blocker only
when the needed tools, permissions, or capabilities are genuinely unavailable,
including the available alternatives assessed and the unmet requirement.
Do not invent a renderer API, bypass project restrictions, or revive retired
rendering routes. Leave platform-specific wiring in the consuming integration.

## Preview, inspect, and repair

Use the authorized tools to produce and actually open a preview. For moving
visuals, inspect playback when available and representative frames around
changes, transitions, and the densest scenes; a successful render exit code
alone is not visual acceptance. Inspect at the intended viewing size.

Check the result against the scene criteria and the supplied narration:

- Is the intended relationship visible without reading the whole narration?
- Are scene changes and motion synchronized with the spoken explanation?
- Are labels, subtitles, units, contrast, and object boundaries readable, with
  no clipping, overlaps, misleading scales, or unsupported factual implications?
- Does each scene explain its particular beat rather than repeat a generic
  layout with swapped text? Does variation still preserve visual continuity?
- Were the visual choices derived from this episode's meaning and argument,
  rather than selected only because a keyword matched a preset shot or image?
- For required motion or audio, does the actual preview demonstrate it rather
  than merely suggest it in a storyboard?

Record concrete defects, fix the relevant scene or timing, render again, and
inspect the changed result and neighboring transitions. Use the caller's
repair budget; if none is supplied, set a bounded local repair budget before
rendering that fits the authorized time and cost. Do not silently downgrade
quality or loop indefinitely when it is exhausted.

If rendering, inspection, playback, evidence, or permission is unavailable,
state exactly which check is blocked. Deliver a plan or inspected stills as
such, not as proof that a video or its motion passed. Static instruction
checks cannot prove that the agent followed the design workflow.

## Handoff

Return the topic-specific scene plan, actual preview/artifact references when
created, checks performed with observations, remaining blockers, and whether
the result is a plan, preview, or reviewed artifact. Keep failed criteria
visible. Hand off to the existing consumer workflow without publishing or
changing its approval state.
