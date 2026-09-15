# ECC evaluation

## Purpose

ECC will later be evaluated as an AI engineering workflow layer. The evaluation should determine whether ECC makes a long-lived software project more reliable, consistent, understandable, verifiable, and easier to resume.

## Experiment goals

The central evaluation question is:

"Does ECC make a long-lived software project more reliable, consistent, understandable, verifiable, and easier to resume?"

The evaluation should consider:
- planning quality
- implementation quality
- human corrections required
- architecture consistency
- defects ECC caught
- defects ECC missed
- verification reliability
- session-to-session memory
- context/token overhead
- unnecessary complexity
- useful agents/skills
- continuous-learning usefulness
- incorrect learned behavior

## ECC role and boundary

FROZEN: ECC may help with:
- planning
- architecture review
- implementation
- testing
- code review
- verification
- memory/context persistence
- continuous learning
- security checks

FROZEN: ECC is not the product owner.

ECC cannot independently redefine accepted business rules, domain concepts, scope, or ADRs.

## Evaluation criteria

The project should assess whether ECC contributes to:
- clarity of decision-making
- consistency with approved product and domain decisions
- reduced drift from source-of-truth documentation
- improved verification discipline
- maintainable long-lived engineering records
- practical learning and reuse across sessions

## Future experiment log template

Use dated entries to record individual experiments and their outcomes.

Example:

### YYYY-MM-DD — Experiment name
- Objective:
- Scope:
- Approach:
- Results:
- Planning quality:
- Implementation quality:
- Human corrections required:
- Architecture consistency:
- Defects caught:
- Defects missed:
- Verification reliability:
- Memory/session continuity:
- Context/token overhead:
- Complexity notes:
- Useful agents/skills:
- Continuous-learning value:
- Incorrect learned behavior:
- Overall assessment:

## Evaluation principle

CURRENT: ECC should be judged by its contribution to long-lived reliability and maintainability, not by its superficial speed in isolated tasks.
