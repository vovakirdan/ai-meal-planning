# PRD: Telegram Meal Planner Bot (MVP)

**Author:** Codex
**Date:** 2026-03-15
**Status:** Draft
**Version:** 1.0
**Taskmaster Optimized:** Yes

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Goals & Success Metrics](#goals--success-metrics)
4. [User Stories](#user-stories)
5. [Functional Requirements](#functional-requirements)
6. [Non-Functional Requirements](#non-functional-requirements)
7. [Technical Considerations](#technical-considerations)
8. [Implementation Roadmap](#implementation-roadmap)
9. [Out of Scope](#out-of-scope)
10. [Open Questions & Risks](#open-questions--risks)
11. [Validation Checkpoints](#validation-checkpoints)
12. [Appendix: Task Breakdown Hints](#appendix-task-breakdown-hints)

---

## Executive Summary

Telegram Meal Planner Bot is an AI-assisted household meal planner for one Telegram account with multiple internal profiles. The MVP helps a user create a weekly meal plan, adjust meals during the week, track pantry state at an approximate level, generate a shopping list, and remember dish feedback. The product goal is not diet coaching or exact macro accounting; it is to reduce weekly decision fatigue and make meal planning usable inside Telegram without a web UI.

---

## Problem Statement

### Current Situation

Household meal planning is usually handled through ad hoc chat messages, memory, notes, and repetitive browsing of recipes. The user has to remember what was cooked recently, what ingredients are already at home, what each household member prefers, and how to adapt when the week changes. This leads to repeated decisions, duplicated purchases, and lower adherence to any plan that was made earlier.

### User Impact

- **Who is affected:** One primary Telegram user managing meals for a household of 1-2 people, with support for several internal profiles such as adults, kids, or special preference sets.
- **Pain points:**
  - The user spends time every week deciding what to cook.
  - The user loses track of liked and disliked dishes.
  - The user buys ingredients without a consolidated plan.
  - The user abandons the plan when one day changes.
  - The user has no single view of "what is planned today" and "what still needs to be bought."
- **Severity:** High for weekly routine adherence, because the workflow repeats every week and creates recurring friction rather than a one-time inconvenience.

### Business Impact

- **Cost of problem:** For this MVP, the main cost is low retention and low perceived value if the bot cannot help the user reach a confirmed weekly plan in one session.
- **Opportunity cost:** Without weekly planning, pantry tracking, and replanning in one flow, the product cannot validate its core value proposition or justify future work on reminders, exports, grocery integrations, or paid tiers.
- **Strategic importance:** This MVP is the foundation for a retained-use product. If the bot cannot support the weekly planning loop, there is no credible path to habit formation, engagement metrics, or later monetization hypotheses.

### Why Solve This Now?

Telegram already provides a low-friction interface for conversational commands, buttons, and compact daily summaries. The scope is narrow enough for an MVP: one Telegram account, multiple internal profiles, approximate pantry state, and weekly planning as the main ritual. This boundary makes it possible to validate the product loop before investing in multi-user household logic or a separate web interface.

---

## Goals & Success Metrics

### Goal 1: Reach a confirmed weekly plan from onboarding

- **Description:** A new user should be able to create a profile and confirm a first weekly plan without leaving Telegram.
- **Metric:** Percentage of users who confirm a weekly plan after completing onboarding.
- **Baseline:** 0%, because the MVP is greenfield.
- **Target:** >= 60% within the first 30 days of private alpha usage.
- **Timeframe:** 30 days after MVP launch.
- **Measurement Method:** Telegram event logs for `/start`, profile creation, plan generation, and plan confirmation.

### Goal 2: Drive repeat interaction during the planned week

- **Description:** Users should return to the bot to check today's meals, open recipes, or replace meals after the plan has been confirmed.
- **Metric:** Percentage of confirmed weekly plans that receive at least one in-week follow-up action.
- **Baseline:** 0 confirmed plans.
- **Target:** >= 70% of confirmed plans have at least one `/today`, `/recipe`, `/replace`, or `/shopping` action within the same week.
- **Timeframe:** First 30 days after MVP launch.
- **Measurement Method:** Logged command usage tied to weekly plan IDs.

### Goal 3: Establish a usable memory loop

- **Description:** The product should collect enough dish feedback to improve future suggestions.
- **Metric:** Percentage of confirmed weekly plans with at least one dish feedback entry.
- **Baseline:** 0%, because feedback storage does not exist yet.
- **Target:** >= 40% within the first 30 days after MVP launch.
- **Timeframe:** 30 days after MVP launch.
- **Measurement Method:** Logged `/rate` actions and stored dish feedback rows.

### Goal 4: Keep planning latency within acceptable MVP limits

- **Description:** The bot should acknowledge user actions promptly and finish generation tasks within a bounded wait time.
- **Metric:** p95 response time for non-AI commands and p95 completion time for plan generation or meal replacement.
- **Baseline:** No existing system.
- **Target:** p95 <= 1.5 seconds for non-AI commands; p95 <= 45 seconds for plan generation; p95 <= 20 seconds for single-meal replacement.
- **Timeframe:** Before MVP release and during the first 30 days after launch.
- **Measurement Method:** Application logs with duration metrics per command and orchestration step.

---

## User Stories

### Story 1: Create and manage household profiles

**As a** Telegram user managing meals for a household,  
**I want to** create one or more meal-planning profiles inside the bot,  
**So that I can** plan meals with different preferences and constraints.

**Acceptance Criteria:**
- [ ] The user can create a profile with name, household size, dislikes, dietary constraints, cuisine preferences, and repeatability mode.
- [ ] The user can switch the active profile without deleting previous data.
- [ ] The bot stores profile preferences and uses the active profile on the next planning session.
- [ ] The bot prevents access to profiles that belong to another Telegram user.

**Task Breakdown Hint:**
- Task 1.1: Create profile and active-profile tables plus repositories (~4h)
- Task 1.2: Build onboarding and profile edit Telegram flows (~6h)
- Task 1.3: Add active-profile resolution middleware (~3h)
- Task 1.4: Add tests for profile CRUD and profile isolation (~4h)

**Dependencies:** None

### Story 2: Generate and confirm a weekly meal plan

**As a** Telegram user,  
**I want to** generate a weekly meal plan that reflects pantry, preferences, and recent history,  
**So that I can** stop deciding meals from scratch every day.

**Acceptance Criteria:**
- [ ] The user can start planning for a target week and provide optional planning notes such as "lighter week", "cheaper week", or "use what is at home".
- [ ] The bot produces a structured draft grouped by day and meal slot.
- [ ] The user can confirm the draft and the bot persists the plan with status `confirmed`.
- [ ] The confirmed plan can be reopened later without regeneration.

**Task Breakdown Hint:**
- Task 2.1: Define planning request and plan aggregate models (~4h)
- Task 2.2: Implement planning orchestration and prompt pipeline (~8h)
- Task 2.3: Persist draft and confirmed plan states (~5h)
- Task 2.4: Add integration tests for plan generation and confirmation (~5h)

**Dependencies:** Story 1, REQ-001, REQ-002

### Story 3: Adjust meals when the week changes

**As a** Telegram user with a confirmed plan,  
**I want to** replace one meal, the rest of a day, or a full day,  
**So that I can** keep the plan usable when time, mood, or ingredients change.

**Acceptance Criteria:**
- [ ] The user can select the replacement scope: one meal, remaining meals for the current day, or all meals for a target day.
- [ ] The bot returns 3-5 replacement options that respect hard constraints and current pantry state.
- [ ] The selected replacement updates the stored plan and records the change in the audit trail.
- [ ] The shopping list can be regenerated from the updated plan.

**Task Breakdown Hint:**
- Task 3.1: Add replacement command and callback handlers (~4h)
- Task 3.2: Implement replacement option generation pipeline (~6h)
- Task 3.3: Persist plan revisions and audit entries (~4h)
- Task 3.4: Add tests for scope-aware replacement behavior (~4h)

**Dependencies:** Story 2, REQ-003, REQ-004

### Story 4: Generate a shopping list from the confirmed plan

**As a** Telegram user,  
**I want to** receive one shopping list grouped by category and adjusted for pantry state,  
**So that I can** shop from the plan rather than from memory.

**Acceptance Criteria:**
- [ ] The bot aggregates ingredients across the confirmed weekly plan.
- [ ] The bot marks each ingredient as `need_to_buy`, `partially_have`, or `already_have`.
- [ ] The shopping list is grouped into household-friendly categories such as produce, dairy, proteins, pantry staples, and treats.
- [ ] The user can reopen the latest shopping list for the active confirmed plan.

**Task Breakdown Hint:**
- Task 4.1: Normalize recipe ingredient records for shopping generation (~5h)
- Task 4.2: Implement shopping list builder with pantry subtraction rules (~6h)
- Task 4.3: Build Telegram rendering for grouped shopping output (~3h)
- Task 4.4: Add tests for ingredient merge and availability states (~4h)

**Dependencies:** Story 2, REQ-007, REQ-008

### Story 5: Record dish feedback and reuse it later

**As a** Telegram user,  
**I want to** mark dishes as favorite, can repeat, rarely repeat, or never again,  
**So that I can** improve future weekly plans without repeating manual explanations.

**Acceptance Criteria:**
- [ ] The bot supports the repeat verdicts `never_again`, `rarely_repeat`, `can_repeat`, and `favorite`.
- [ ] The feedback entry can include optional notes such as "too expensive" or "too much prep".
- [ ] The next weekly planning request uses the last 30 days of dish history plus all explicit favorite and never-again signals.
- [ ] A dish marked `never_again` is excluded from future generated plans unless the user explicitly overrides it.

**Task Breakdown Hint:**
- Task 5.1: Create dish history and feedback models (~4h)
- Task 5.2: Add Telegram feedback actions and storage (~4h)
- Task 5.3: Inject history and feedback signals into planning context (~5h)
- Task 5.4: Add tests for feedback weighting and exclusion rules (~4h)

**Dependencies:** Story 2, REQ-009, REQ-010

---

## Functional Requirements

### Must Have (P0) - Critical for Launch

#### REQ-001: Telegram user onboarding and profile creation

**Description:** The system must onboard a Telegram user and create at least one planning profile tied to that Telegram account.

**Acceptance Criteria:**
- [ ] `/start` creates or loads a user record bound to `telegram_user_id`.
- [ ] The onboarding flow collects profile name, household size, dislikes, dietary constraints, cuisine preferences, dessert preferences, and repeatability mode.
- [ ] The system stores the created profile and marks it as active.
- [ ] A Telegram user cannot read or modify data owned by another Telegram user.

**Technical Specification:**
```typescript
interface CreateProfileRequest {
  telegramUserId: string;
  name: string;
  householdSize: number;
  dislikes: string[];
  constraints: string[];
  cuisines: string[];
  dessertPreferences: string[];
  repeatabilityMode: "balanced" | "more_variety" | "more_repeatability";
}
```

**Task Breakdown:**
- Implement user and profile persistence: Medium (6h)
- Build onboarding command and callback flow: Medium (6h)
- Add active-profile selection logic: Small (3h)
- Test account isolation: Small (3h)

**Dependencies:** None

#### REQ-002: Multiple profiles inside one Telegram account

**Description:** The system must support several internal profiles for one Telegram account and let the user switch the active profile.

**Acceptance Criteria:**
- [ ] The user can list profiles via `/profiles`.
- [ ] The user can switch the active profile via `/switch_profile`.
- [ ] All planning, pantry, history, and shopping data are stored per profile.
- [ ] The last active profile is reused on the next bot interaction.

**Task Breakdown:**
- Implement profile listing and activation handlers: Small (4h)
- Add profile-scoped repositories and services: Medium (5h)
- Add regression tests for profile switching: Small (3h)

**Dependencies:** REQ-001

#### REQ-003: Weekly plan generation

**Description:** The system must generate a seven-day meal plan for the active profile, using preferences, pantry state, and recent history as structured context.

**Acceptance Criteria:**
- [ ] `/plan_week` accepts an optional week start date and optional planning notes.
- [ ] The generated draft groups meals by day and meal type.
- [ ] The planning pipeline enforces hard exclusions from profile constraints and `never_again` feedback.
- [ ] The draft includes a short dish summary and a recipe reference or generated recipe payload for each meal.

**Technical Specification:**
```typescript
interface WeeklyPlanDraft {
  profileId: string;
  weekStartDate: string;
  status: "draft";
  days: Array<{
    date: string;
    meals: Array<{
      mealType: "meal" | "snack" | "dessert";
      slotLabel: string | null;
      dishName: string;
      dishSummary: string;
      recipeRef: string | null;
      balanceNote: string | null;
    }>;
  }>;
}
```

**Task Breakdown:**
- Create planning request and draft models: Small (4h)
- Build LLM prompt assembly with profile, pantry, and history context: Large (8h)
- Add hard-constraint validation for generated meals: Medium (5h)
- Add integration tests for weekly generation: Medium (5h)

**Dependencies:** REQ-001, REQ-002, REQ-006, REQ-010

#### REQ-004: Plan review, replacement, and confirmation

**Description:** The system must let the user review a draft, replace parts of the plan, and confirm the final weekly plan.

**Acceptance Criteria:**
- [ ] The draft view exposes actions to replace one meal, replace a target day, or replace remaining meals for the current day.
- [ ] Replacement requests return 3-5 alternatives that satisfy hard constraints.
- [ ] Confirming the plan changes status from `draft` to `confirmed`.
- [ ] Every confirmed replacement is recorded in a plan audit log with timestamp and scope.

**Task Breakdown:**
- Add draft rendering and action callbacks: Medium (5h)
- Implement replacement orchestration by scope: Medium (6h)
- Persist audit trail and plan status transitions: Medium (5h)
- Add tests for confirmation and replacement flows: Medium (5h)

**Dependencies:** REQ-003

#### REQ-005: Today view for the active plan

**Description:** The system must provide a compact "today" view for the active confirmed plan.

**Acceptance Criteria:**
- [ ] `/today` returns the meals planned for the current local date.
- [ ] Each meal in the response includes dish name, meal type, and available actions for recipe, replace, mark prepared, and rate.
- [ ] If no confirmed plan exists for the current week, the bot returns a clear recovery path to `/plan_week`.
- [ ] The today view uses the active profile only.

**Task Breakdown:**
- Implement current-week plan lookup: Small (3h)
- Build today-view Telegram rendering: Small (4h)
- Add empty-state handling and tests: Small (3h)

**Dependencies:** REQ-004

#### REQ-006: Pantry tracking with approximate quantities

**Description:** The system must support pantry tracking at an approximate level rather than exact stock accounting.

**Acceptance Criteria:**
- [ ] The user can add pantry items manually through `/pantry`.
- [ ] Each pantry item supports `has`, `low`, `empty`, or an approximate quantity with unit.
- [ ] The user can edit or clear pantry items manually.
- [ ] Planning and shopping logic can read pantry state for the active profile.

**Technical Specification:**
```typescript
interface PantryItem {
  profileId: string;
  ingredientName: string;
  stockLevel: "has" | "low" | "empty" | "unknown";
  quantityValue: number | null;
  quantityUnit: "g" | "kg" | "ml" | "l" | "pcs" | null;
  notes: string | null;
}
```

**Task Breakdown:**
- Create pantry storage schema and CRUD services: Medium (5h)
- Build pantry command and edit flows: Medium (5h)
- Add pantry context formatter for planning and shopping: Small (3h)
- Add tests for pantry state transitions: Small (3h)

**Dependencies:** REQ-001, REQ-002

#### REQ-007: Recipe storage and retrieval

**Description:** The system must store recipe ingredients, preparation steps, and timing for planned dishes.

**Acceptance Criteria:**
- [ ] Each planned dish stores or references a recipe object with ingredients and ordered steps.
- [ ] `/recipe` returns a full recipe for a selected dish.
- [ ] The plan view can show a short recipe summary without loading the full step list.
- [ ] Recipe data is linked to the active weekly plan and can be reused during shopping generation.

**Task Breakdown:**
- Define recipe schema and repository: Small (4h)
- Add recipe persistence during plan generation: Medium (5h)
- Implement `/recipe` command and selection flow: Small (4h)
- Add tests for recipe lookup and rendering: Small (3h)

**Dependencies:** REQ-003

#### REQ-008: Shopping list generation

**Description:** The system must generate a shopping list from the confirmed plan and pantry state.

**Acceptance Criteria:**
- [ ] `/shopping` aggregates recipe ingredients across the active confirmed weekly plan.
- [ ] Duplicate ingredients are merged by normalized ingredient key.
- [ ] The result groups items by category and marks each item as `need_to_buy`, `partially_have`, or `already_have`.
- [ ] Replanning or pantry edits can trigger shopping list regeneration for the same weekly plan.

**Task Breakdown:**
- Implement ingredient normalization rules: Medium (6h)
- Build shopping list generator and category mapping: Medium (6h)
- Add regeneration after plan change or pantry change: Small (3h)
- Add tests for merge and availability logic: Medium (5h)

**Dependencies:** REQ-004, REQ-006, REQ-007

#### REQ-009: Dish feedback and repeat verdicts

**Description:** The system must record dish-level feedback that influences future planning.

**Acceptance Criteria:**
- [ ] `/rate` or inline actions can store `never_again`, `rarely_repeat`, `can_repeat`, or `favorite`.
- [ ] Optional free-text notes are stored with the feedback entry.
- [ ] Feedback is stored against profile and dish identity.
- [ ] Dish history records whether the dish was planned, eaten, skipped, or replaced.

**Task Breakdown:**
- Create dish history and feedback tables: Medium (5h)
- Build rating actions and free-text note capture: Medium (5h)
- Link feedback writes to completed or viewed meals: Small (3h)
- Add tests for verdict storage and retrieval: Small (4h)

**Dependencies:** REQ-003, REQ-005

#### REQ-010: History-aware planning context

**Description:** The planning engine must use recent dish history and explicit repeat verdicts to increase variety and avoid unwanted repetition.

**Acceptance Criteria:**
- [ ] The planning request includes dish history for the last 30 days.
- [ ] `favorite` dishes can increase in ranking weight.
- [ ] `never_again` dishes are excluded unless the user explicitly asks for them.
- [ ] The repeatability mode changes weighting between recent-history penalty and favorite reuse.

**Task Breakdown:**
- Define ranking inputs from history and feedback: Medium (5h)
- Inject ranking inputs into prompt assembly: Medium (4h)
- Add tests for verdict-driven inclusion and exclusion: Small (4h)

**Dependencies:** REQ-003, REQ-009

#### REQ-011: Structured Telegram UX with commands and buttons

**Description:** The Telegram UX must support both command entry points and button-driven progression for all launch-critical scenarios.

**Acceptance Criteria:**
- [ ] `/start`, `/profiles`, `/setup`, `/plan_week`, `/menu`, `/today`, `/replace`, `/shopping`, `/pantry`, `/recipe`, `/rate`, and `/help` are available.
- [ ] Every launch-critical flow can be completed through buttons and guided prompts after the initial command.
- [ ] The bot keeps individual messages under 4,000 Telegram characters.
- [ ] Long outputs such as weekly plans and shopping lists are split into several messages when needed.

**Task Breakdown:**
- Define command router and callback namespace: Medium (4h)
- Build reusable Telegram message composers: Medium (5h)
- Add output splitting and pagination helpers: Small (3h)
- Add tests for command routing and message-size handling: Small (4h)

**Dependencies:** REQ-001, REQ-003, REQ-004, REQ-008

### Should Have (P1) - Important but Not Blocking Launch

#### REQ-012: Weekly reminder scheduling

**Description:** The system should support one weekly reminder per active profile to start a new planning cycle.

**Acceptance Criteria:**
- [ ] The user can enable or disable a weekly reminder day and time.
- [ ] The reminder is stored per profile.
- [ ] The reminder sends one Telegram message with an entry point to `/plan_week`.

**Task Breakdown:**
- Add reminder preference fields: Small (3h)
- Add scheduler integration and delivery job: Medium (5h)
- Add tests for reminder scheduling and idempotency: Small (3h)

**Dependencies:** REQ-001, REQ-002

---

## Non-Functional Requirements

### Performance

- Non-AI commands such as `/today`, `/profiles`, and `/help` must return a first full response in <= 1.5 seconds at p95.
- Pantry update and feedback write operations must complete in <= 2 seconds at p95.
- Weekly plan generation must complete in <= 45 seconds at p95.
- Single-meal replacement must complete in <= 20 seconds at p95.

### Reliability

- Confirmed weekly plans must survive application restarts with zero data loss from committed database transactions.
- If LLM generation fails, the user must receive a recoverable error message and a retry path within 5 seconds of failure detection.
- Shopping list regeneration must be idempotent for the same plan revision and pantry snapshot.

### Security and Data Handling

- Every database query for user-owned data must include the Telegram user scope.
- The application must never return another user's profile, plan, pantry, shopping list, or feedback data.
- API keys and bot tokens must not be written to application logs.
- Bot webhooks or polling credentials must be loaded from environment variables or secret storage, not from source code.

### Cost and Resource Use

- One weekly plan generation should use <= 3 model calls for the happy path.
- One single-meal replacement should use <= 2 model calls for the happy path.
- Application memory for the bot process should stay under 512 MB in a single-instance MVP deployment.

### Observability

- The system must log profile creation, plan generation start, plan generation completion, plan confirmation, pantry update, shopping list generation, and dish feedback events.
- Each logged event must include timestamp, Telegram user ID, profile ID when available, and correlation ID for the current request.
- Health endpoints must expose bot status, database connectivity, and Redis connectivity when Redis is enabled.

### Compatibility

- The product must support Telegram clients on iOS, Android, desktop, and web through standard bot interactions.
- All message layouts must remain readable in narrow mobile chat widths without requiring a separate web view.

---

## Technical Considerations

### System Architecture

**Current Architecture:** Greenfield project with TaskMaster initialized and no production code yet.

**Proposed Architecture:** A Telegram bot layer routes commands and button callbacks into an application service layer. The application layer owns profile management, plan orchestration, replanning, pantry operations, shopping list generation, and feedback storage. An AI provider layer generates plan drafts, replacements, recipe payloads, and summary notes. PostgreSQL stores durable product state. Redis is recommended for FSM/session state and short-lived orchestration context, but the design must still run without Redis in the earliest local setup.

**Diagram:**
```text
Telegram Client
      |
      v
Telegram Bot Adapter (aiogram)
      |
      v
Application Services
- ProfileService
- PlanningService
- ReplanningService
- PantryService
- ShoppingListService
- FeedbackService
      |
      +----------------------+
      |                      |
      v                      v
LLM Provider Adapter      Persistence Layer
                          - PostgreSQL
                          - Redis (optional at first launch)
```

**Key Components:**
1. **Telegram Bot Adapter:** Handles commands, callbacks, and message formatting.
2. **Planning Orchestrator:** Builds context, invokes the model, validates the output, and stores drafts.
3. **Constraint Validator:** Applies hard exclusions and detects invalid generated dishes before showing them to the user.
4. **Persistence Layer:** Stores profiles, plans, pantry items, recipes, shopping lists, history, and feedback.
5. **Audit/Event Logger:** Records user actions and orchestration durations for diagnostics and metrics.

### Data Model

**Core Tables:**

```sql
users(
  id uuid primary key,
  telegram_user_id bigint unique not null,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

profiles(
  id uuid primary key,
  user_id uuid not null references users(id),
  name text not null,
  household_size integer not null,
  is_active boolean not null default false,
  preferences_json jsonb not null,
  constraints_json jsonb not null,
  repeatability_mode text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

weekly_plans(
  id uuid primary key,
  profile_id uuid not null references profiles(id),
  week_start_date date not null,
  week_end_date date not null,
  status text not null check (status in ('draft', 'confirmed', 'archived')),
  weekly_notes text null,
  revision integer not null default 1,
  created_at timestamptz not null,
  updated_at timestamptz not null
);

planned_meals(
  id uuid primary key,
  weekly_plan_id uuid not null references weekly_plans(id),
  meal_date date not null,
  meal_type text not null check (meal_type in ('meal', 'snack', 'dessert')),
  meal_slot_label text null,
  dish_name text not null,
  dish_summary text not null,
  recipe_id uuid null,
  status text not null check (status in ('planned', 'replaced', 'prepared', 'skipped')),
  created_at timestamptz not null,
  updated_at timestamptz not null
);
```

**Supporting Tables:**
- `recipes`
- `pantry_items`
- `shopping_lists`
- `shopping_list_items`
- `dish_feedback`
- `dish_history`
- `plan_audit_events`

### Telegram Interaction Model

- Entry points use Telegram commands.
- Most follow-up steps use inline buttons and guided prompts.
- The bot should minimize free-text parsing after the entry point and reserve it for planning notes or feedback notes.
- Multi-step flows should use FSM/session state with expiration to prevent stale callbacks from mutating current plans.

### AI Responsibilities vs Backend Responsibilities

**AI responsibilities:**
- Interpret planning notes and user intent.
- Draft weekly menus and replacement candidates.
- Draft recipe summaries and structured ingredients when not already present.
- Produce short balance notes for the week or meal.

**Backend responsibilities:**
- Store and retrieve all durable state.
- Enforce hard exclusions, profile isolation, and plan status transitions.
- Normalize ingredients and build shopping lists.
- Maintain audit trails, metrics, and validation before persistence.

### Technology Stack

- **Language:** Python 3.12+
- **Bot Framework:** aiogram
- **API/Application Layer:** FastAPI for service endpoints and health checks
- **Database:** PostgreSQL 16+
- **ORM:** SQLAlchemy 2.x or SQLModel
- **Cache / Session State:** Redis 7+ recommended
- **Containerization:** Docker Compose for local development
- **Testing:** pytest, pytest-asyncio, and integration tests against PostgreSQL

### External Dependencies

1. **Telegram Bot API**
   - Purpose: bot updates, commands, callbacks, outbound messages
   - Failure handling: retry transient failures; record delivery errors

2. **LLM Provider via Codex CLI-backed TaskMaster setup**
   - Purpose: planning drafts, replacements, recipe drafting, summary notes
   - Failure handling: return recoverable error, keep previous confirmed plan unchanged

3. **Redis (optional for first local run)**
   - Purpose: FSM state, orchestration state, ephemeral caching
   - Failure handling: support local development with in-memory fallback where practical

### Migration Strategy

This is a greenfield MVP. No legacy data migration is required before first release. The first production deployment should apply schema creation migrations only.

### Testing Strategy

- **Unit Tests:** ranking logic, pantry normalization, ingredient merging, validators, command-to-service mapping
- **Integration Tests:** profile CRUD, plan generation persistence, replacement flows, shopping regeneration, feedback storage
- **End-to-End Tests:** onboarding -> plan -> confirm -> today -> replace -> shopping -> rate
- **Load Checks:** synthetic plan generation and replacement durations under representative local and staging conditions

---

## Implementation Roadmap

### Phase 1: Foundations

**Goal:** Create durable product state, Telegram entry points, and profile management.

**Tasks:**
- Task 1.1: Create database schema for users, profiles, pantry, plans, recipes, and feedback
- Task 1.2: Set up aiogram bot shell and command router
- Task 1.3: Implement onboarding and active-profile flows
- Task 1.4: Add health checks and base logging

**Validation Checkpoint:** User can start the bot, create a profile, switch profiles, and keep profile data after restart.

### Phase 2: Planning Loop

**Goal:** Generate draft weekly plans, show them in Telegram, and confirm them.

**Tasks:**
- Task 2.1: Implement planning orchestration and prompt assembly
- Task 2.2: Persist draft weekly plans and planned meals
- Task 2.3: Build review UI and confirmation flow
- Task 2.4: Store recipes attached to planned dishes

**Validation Checkpoint:** User can generate a weekly draft and confirm it for the active profile.

### Phase 3: Replanning and Shopping

**Goal:** Keep the plan usable during the week and connect it to pantry-aware shopping output.

**Tasks:**
- Task 3.1: Implement today view
- Task 3.2: Implement scoped replacement flows
- Task 3.3: Build pantry CRUD
- Task 3.4: Build shopping list generation and regeneration

**Validation Checkpoint:** User can replace one meal or one day, update pantry, and regenerate the shopping list.

### Phase 4: Memory Loop and Release Readiness

**Goal:** Add dish feedback, history-aware planning, tests, and release instrumentation.

**Tasks:**
- Task 4.1: Implement dish feedback and dish history
- Task 4.2: Integrate history and verdict weighting into planning
- Task 4.3: Add integration and end-to-end tests
- Task 4.4: Verify metrics, latency targets, and release checklist

**Validation Checkpoint:** The next plan reflects history and repeat verdicts, and release criteria pass in staging.

### Task Dependencies Visualization

```text
REQ-001 -> REQ-002 -> REQ-003 -> REQ-004 -> REQ-005
REQ-001 -> REQ-006
REQ-003 -> REQ-007
REQ-004 + REQ-006 + REQ-007 -> REQ-008
REQ-003 + REQ-005 -> REQ-009
REQ-003 + REQ-009 -> REQ-010
REQ-001 + REQ-003 + REQ-004 + REQ-008 -> REQ-011
REQ-001 + REQ-002 -> REQ-012
```

### Effort Estimation

- Phase 1: ~20 hours
- Phase 2: ~28 hours
- Phase 3: ~27 hours
- Phase 4: ~24 hours
- Total implementation effort: ~99 hours
- Risk buffer: +20 hours
- Final estimate: ~119 hours

---

## Out of Scope

Explicitly excluded from the MVP release:

1. Multi-account household collaboration where several Telegram accounts edit the same plan.
2. Automatic grocery ordering or direct store integrations.
3. Exact macro accounting, medical nutrition advice, or disease-specific diet plans.
4. Full stock accounting by batch, expiration date, or automatic deduction from recipes.
5. Native web or mobile companion interface.
6. OCR receipts, barcode scanning, or kitchen-device integrations.
7. Budget optimization by live market prices.
8. Calendar integrations with Google Calendar, Apple Calendar, or similar.

---

## Open Questions & Risks

### Open Questions

#### Q1: Weekly reminder timing

- **Current Status:** Deferred to P1 requirement.
- **Options:** disabled by default, user-configured weekly reminder, fixed reminder after plan confirmation
- **Owner:** Product decision during post-MVP prioritization
- **Impact:** Low for launch, medium for retention work

#### Q2: Planning horizon variants

- **Current Status:** MVP default is one week.
- **Options:** fixed 7-day plans only, 3-day short plan mode, custom range length
- **Owner:** Product decision after first usage data
- **Impact:** Medium because it changes prompt structure and plan storage rules

#### Q3: Leftovers and batch cooking

- **Current Status:** Excluded from MVP.
- **Options:** no leftovers, manual leftovers tag, generated leftovers planning
- **Owner:** Product decision after MVP
- **Impact:** Medium because it changes recipe, pantry, and shopping semantics

### Risks & Mitigation

| Risk | Likelihood | Impact | Severity | Mitigation | Contingency |
|------|------------|--------|----------|------------|-------------|
| Generated dishes conflict with hard constraints | Medium | High | High | Validate every generated meal before presenting it | Retry generation with rejection reasons |
| Shopping list normalization produces duplicate or fragmented items | High | Medium | High | Build normalized ingredient keys and integration tests | Let user regenerate after normalization fixes |
| Pantry upkeep feels too heavy for users | Medium | Medium | Medium | Keep pantry states approximate and manual | Allow planning without pantry data |
| Replacement flow breaks plan consistency | Medium | High | High | Persist revisions and recalculate shopping lists from the new revision | Keep previous confirmed revision available for rollback |
| Telegram message size or layout becomes unreadable | Medium | Medium | Medium | Compose compact sections and split long payloads | Paginate weekly plan and shopping output |

---

## Validation Checkpoints

### Validation Checkpoint 1: Foundations complete

**Criteria:**
- [ ] User can complete onboarding
- [ ] User can create and switch profiles
- [ ] Profile isolation tests pass
- [ ] Core tables exist and pass migration checks

### Validation Checkpoint 2: Weekly planning works

**Criteria:**
- [ ] User can generate a weekly draft
- [ ] User can confirm a weekly plan
- [ ] Recipes are stored and retrievable
- [ ] p95 plan generation stays within 45 seconds in staging

### Validation Checkpoint 3: Mid-week interaction works

**Criteria:**
- [ ] `/today` returns the active day's meals
- [ ] Meal replacement updates the stored plan revision
- [ ] Shopping list regeneration reflects the new plan revision
- [ ] Pantry edits affect the next shopping output

### Validation Checkpoint 4: Memory loop works

**Criteria:**
- [ ] Dish feedback is stored
- [ ] History from the last 30 days is visible to the planning engine
- [ ] `never_again` dishes are excluded from generated plans
- [ ] Integration tests for feedback and ranking pass

### Validation Checkpoint 5: Release readiness

**Criteria:**
- [ ] Launch-critical commands are available
- [ ] Health checks report database status
- [ ] Event logging covers core product actions
- [ ] Release checklist and smoke tests pass

---

## Appendix: Task Breakdown Hints

### Suggested TaskMaster Task Structure

1. Bootstrap bot application shell and configuration
2. Create database schema and migrations
3. Implement user and profile management
4. Implement pantry storage and CRUD
5. Implement planning orchestration and validators
6. Implement weekly plan persistence and review UI
7. Implement recipe storage and retrieval
8. Implement today view
9. Implement replacement flows and plan revision tracking
10. Implement shopping list generation
11. Implement dish feedback and history
12. Integrate history-aware ranking into planning
13. Add logging, health checks, and metrics
14. Add integration and end-to-end tests
15. Prepare staging checklist and release verification

### Parallelizable Work

- Profile management and pantry CRUD can proceed in parallel after the base schema exists.
- Recipe retrieval and today-view rendering can proceed in parallel after weekly plan persistence exists.
- Observability and test harness work can proceed in parallel with feature completion in later phases.

### Critical Path

1. REQ-001 onboarding
2. REQ-002 profile activation
3. REQ-006 pantry storage
4. REQ-003 weekly planning
5. REQ-004 plan confirmation and replacement
6. REQ-007 recipe storage
7. REQ-008 shopping generation
8. REQ-009 feedback
9. REQ-010 history-aware planning
10. Release verification

### Notes for Task Generation

- Keep profile isolation and hard-constraint validation visible in early tasks.
- Treat shopping generation as a first-class feature, not a post-processing detail.
- Insert a user validation task after each 4-5 implementation tasks.
- Preserve one confirmed plan revision before applying replacements so rollback remains possible.

---

**End of PRD**

This document converts the original product draft into a TaskMaster-oriented PRD with numbered requirements, measurable targets, dependency mapping, and validation checkpoints for Telegram Meal Planner Bot MVP.
