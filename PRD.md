# PRD: Telegram Meal Planner Bot (MVP)

**Version:** 1.0
**Date:** 2026-03-15
**Status:** Draft for review
**Platform:** Telegram Bot
**Primary goal:** бытовое удобство в планировании питания на неделю для одного household с поддержкой нескольких профилей

---

## 1. Overview

`Telegram Meal Planner Bot` — Telegram-бот для планирования питания на неделю с учетом предпочтений, ограничений, приблизительного баланса питания, истории блюд и текущих запасов продуктов дома.

Бот не является нутрициологом, медицинским советником или профессиональным chef assistant. Это бытовой AI meal planner, который помогает заранее продумать меню, согласовать блюда, собрать список покупок и не забывать, что уже есть дома.

---

## 2. Product goals

### 2.1 Primary goals

* Упростить недельное планирование питания.
* Снизить бытовую нагрузку на принятие решений “что есть сегодня / завтра / на неделе”.
* Учитывать предпочтения, ограничения и историю оценок блюд.
* Помогать избегать пищевых “срывов” за счет заранее продуманного плана.
* Давать понятный список покупок на основании меню и уже имеющихся запасов.
* Поддерживать быстрый replanning, если планы на день изменились.

### 2.2 Secondary goals

* Хранить приблизительную память о запасах дома.
* Давать рецепты и краткие инструкции по приготовлению.
* Поддерживать несколько профилей в рамках одного Telegram-аккаунта.
* Давать не точный, а разумный пищевой баланс по неделе и по дню.

### 2.3 Non-goals for MVP

* Медицинские рекомендации, лечебные диеты, диагнозы.
* Точный профессиональный расчет КБЖУ и микронутриентов.
* Автоматическая покупка продуктов в магазинах.
* Полноценный multi-user household с отдельными Telegram-аккаунтами.
* Интеграция с доставками, маркетплейсами и grocery APIs.
* Складской учет по граммам, срокам годности и партиям.
* Автоматическое общение с женой через отдельный подтверждаемый flow.

---

## 3. Problem statement

Пользователь сталкивается с типичными бытовыми проблемами:

* непонятно, что есть в течение недели;
* сложно соблюдать баланс питания без избыточного контроля;
* при смене планов легко сорваться на случайные перекусы;
* продукты покупаются бессистемно;
* забываются удачные и неудачные блюда;
* сложно учитывать, что уже есть дома;
* приготовление и закупка не синхронизированы с реальной жизнью.

---

## 4. Target user

### 4.1 Primary user

Человек, который хочет заранее продумывать питание на неделю, но без жесткого нутрициологического режима.

### 4.2 Usage context

* household из 1–2 человек;
* один Telegram-аккаунт как основной интерфейс;
* несколько профилей внутри одного аккаунта;
* weekly planning как основной ритуал;
* быстрые изменения плана в течение недели.

---

## 5. Product principles

1. **Convenience first**
   Бот должен помогать в быту, а не усложнять его.

2. **Approximate, but useful**
   Не идеальная точность, а полезная практическая адекватность.

3. **Weekly planning as the default mode**
   Неделя — основная единица планирования.

4. **Structured memory over pure chat history**
   Память должна храниться как данные, а не как длинный текст в LLM.

5. **AI for generation, backend for truth**
   ИИ генерирует предложения и адаптирует блюда, backend хранит состояние и ограничения.

6. **Fast replanning matters**
   План должен легко меняться без пересборки всей недели.

---

## 6. Core use cases

### 6.1 Weekly planning

Пользователь просит составить меню на неделю, указывает пожелания, получает draft меню, правит его и подтверждает.

### 6.2 Today view

Пользователь запрашивает блюда на сегодня и краткий план по текущему дню.

### 6.3 Shopping list generation

После утверждения меню бот формирует список покупок с учетом имеющихся продуктов.

### 6.4 Recipe handoff

Пользователь получает список рецептов и может запросить полный рецепт по конкретному блюду.

### 6.5 Pantry awareness

Пользователь вносит, какие продукты есть дома, и бот использует их при планировании.

### 6.6 Dish feedback

После приготовления или употребления блюда пользователь ставит оценку и оставляет комментарий.

### 6.7 Fast replanning

Если день изменился, бот быстро заменяет блюдо, часть дня или целый день, не ломая всю неделю.

---

## 7. Scope of MVP

### 7.1 Included in MVP

* Telegram bot interface.
* Один Telegram user account.
* Несколько профилей внутри одного аккаунта.
* Создание и редактирование профиля.
* Планирование на неделю.
* Планирование произвольного количества приемов пищи в день.
* Поддержка desserts / treats как отдельного типа приема пищи.
* Учет пожеланий на текущую неделю.
* Учет приблизительных запасов продуктов.
* Учет истории блюд за ограниченный период.
* Согласование меню и замена блюд.
* Список покупок по категориям.
* Краткие и полные рецепты.
* Оценка блюд и базовая память.
* Команды для “что сегодня”, “перепланировать”, “список покупок”, “рецепт”.

### 7.2 Excluded from MVP

* Календарные интеграции.
* Mobile/web dashboard.
* Семейный multi-account режим.
* OCR чеков, штрихкоды, smart fridge.
* Цена по магазинам.
* Автоматическое списание запасов без подтверждения.
* Push/reminder engine beyond simple Telegram scheduled reminders.

---

## 8. User flows

## 8.1 Onboarding flow

### Goal

Создать первый профиль и подготовить бота к работе.

### Steps

1. Пользователь запускает `/start`.
2. Бот объясняет, что умеет:

   * составить меню на неделю;
   * учитывать предпочтения и ограничения;
   * помнить блюда и продукты дома;
   * собирать список покупок.
3. Бот предлагает создать профиль.
4. Пользователь задает:

   * имя профиля;
   * количество человек в профиле;
   * общие предпочтения;
   * ограничения;
   * нежелательные продукты;
   * treats/desserts preferences;
   * режим по умолчанию: больше разнообразия / больше повторяемости / сбалансированно.
5. Бот предлагает внести стартовые продукты дома.
6. Профиль сохраняется.

### Result

Пользователь готов к weekly planning.

---

## 8.2 Weekly planning flow

### Goal

Собрать недельное меню.

### Inputs

* профиль;
* временной диапазон недели;
* пожелания на неделю;
* ограничения;
* pantry state;
* history;
* настройки разнообразия/повторяемости.

### Steps

1. Пользователь вызывает `/plan_week` или нажимает “Составить меню”.
2. Бот уточняет:

   * на какие дни планировать;
   * сколько приемов пищи в среднем ожидается;
   * есть ли особые пожелания на неделю;
   * нужен ли “подешевле”, “полегче”, “поинтереснее”, “детокс”, “фестиваль бургеров” и т.д.;
   * что уже есть дома.
3. Бот генерирует черновик меню по дням.
4. Бот показывает план структурированно:

   * день;
   * приемы пищи;
   * блюдо;
   * краткое описание;
   * approximate balance note.
5. Пользователь может:

   * заменить блюдо;
   * заменить день;
   * заменить только один прием пищи;
   * сделать дешевле;
   * сделать проще;
   * сделать с учетом имеющихся продуктов;
   * добавить dessert/treat;
   * увеличить/уменьшить разнообразие.
6. После правок пользователь подтверждает меню.
7. Бот сохраняет меню, рецепты и shopping list.

### Result

Есть утвержденный weekly plan.

---

## 8.3 Today view flow

### Goal

Быстро понять, что есть сегодня.

### Steps

1. Пользователь вызывает `/today`.
2. Бот показывает:

   * все приемы пищи на сегодня;
   * краткие названия блюд;
   * статус готовности;
   * подсказку, что нужно достать/докупить;
   * доступные быстрые действия:

     * рецепт;
     * заменить;
     * отметить как приготовлено;
     * пропустить;
     * сдвинуть.

### Result

Пользователь быстро ориентируется в текущем дне.

---

## 8.4 Fast replanning flow

### Goal

Подменить план, если обстоятельства изменились.

### Scenarios

* нет времени;
* не хочется текущее блюдо;
* не хватает ингредиентов;
* нужен быстрый вариант;
* нужен comfort food / healthy switch / cheaper alternative.

### Steps

1. Пользователь нажимает “Заменить”.
2. Бот уточняет scope:

   * текущее блюдо;
   * весь день;
   * остаток дня.
3. Бот предлагает 3–5 альтернатив, приоритизируя:

   * pantry;
   * историю оценок;
   * баланс недели;
   * текущие пожелания.
4. Пользователь выбирает вариант.
5. Бот обновляет weekly plan и shopping implications.

### Result

План остается живым, а не “сломался и забыт”.

---

## 8.5 Shopping list flow

### Goal

Получить список продуктов на основе утвержденного меню.

### Steps

1. Пользователь вызывает `/shopping`.
2. Бот собирает ингредиенты по всем блюдам недели.
3. Бот вычитает продукты, отмеченные как имеющиеся дома.
4. Бот группирует список:

   * овощи и фрукты;
   * молочное;
   * мясо / рыба;
   * бакалея;
   * специи / соусы;
   * treats / snacks / desserts.
5. Бот показывает:

   * что купить;
   * что уже есть;
   * что, вероятно, не хватает частично.

### Result

Есть практичный shopping list.

---

## 8.6 Dish feedback flow

### Goal

Улучшать будущие рекомендации.

### Steps

1. После дня или после недели бот предлагает оценить блюда.
2. Для каждого блюда пользователь может выбрать:

   * больше не предлагать;
   * редко повторять;
   * можно повторить;
   * любимое.
3. Дополнительно:

   * слишком долго;
   * слишком сложно;
   * суховато;
   * дорого;
   * отлично для повтора;
   * ок, но не скоро.
4. Бот сохраняет оценку.

### Result

Память становится полезнее.

---

## 9. Functional requirements

## 9.1 Profiles

Система должна:

* поддерживать несколько профилей внутри одного Telegram account;
* позволять выбрать активный профиль;
* хранить для профиля:

  * display name;
  * household size;
  * общие предпочтения;
  * ограничения;
  * dislikes;
  * favorite cuisines;
  * treat preferences;
  * repeatability/diversity mode.

## 9.2 Planning engine

Система должна:

* уметь планировать меню на неделю;
* поддерживать нефиксированное число приемов пищи;
* учитывать desserts/treats;
* учитывать ограничения профиля;
* учитывать pantry state;
* учитывать историю последних недель;
* обеспечивать базовую сбалансированность по неделе;
* не строить экстремально несбалансированные дни;
* уметь реагировать на директивы:

  * подешевле;
  * попроще;
  * полезнее;
  * сытнее;
  * разнообразнее;
  * повторить удачное;
  * использовать то, что есть дома.

## 9.3 Meal types

Система должна поддерживать типы:

* meal;
* snack;
* dessert/treat.

Система не должна жестко зашивать только breakfast/lunch/dinner.

## 9.4 Recipes

Система должна:

* хранить краткое описание блюда;
* хранить список ингредиентов;
* хранить шаги приготовления;
* хранить approximate prep/cook time;
* уметь отдавать краткий рецепт и полный рецепт.

## 9.5 Pantry

Система должна:

* позволять вручную добавлять продукты в pantry;
* поддерживать приблизительные остатки:

  * есть;
  * мало;
  * меньше N грамм / мл / штук;
* позволять уменьшать/обнулять остатки вручную;
* учитывать pantry при генерации shopping list;
* учитывать pantry при replanning.

## 9.6 Shopping list

Система должна:

* объединять одинаковые ингредиенты;
* нормализовать близкие позиции, где возможно;
* учитывать pantry;
* разделять “нужно купить” и “уже есть”;
* показывать частично имеющиеся продукты.

## 9.7 Memory and feedback

Система должна:

* хранить историю меню;
* хранить оценки блюд;
* хранить признаки:

  * never again;
  * rarely repeat;
  * can repeat;
  * favorite;
* использовать историю за последние 30 дней как основной контекст разнообразия;
* дополнительно учитывать явно помеченные favorite / never again без ограничения по времени.

## 9.8 Today and replanning

Система должна:

* показывать текущий день;
* уметь заменить одно блюдо;
* уметь заменить остаток дня;
* уметь заменить весь день;
* уметь обновить shopping implications после replanning.

## 9.9 Result handoff

Система должна:

* выдавать финальный weekly plan;
* выдавать полный shopping list;
* выдавать рецепты по запросу;
* поддерживать удобный формат пересылки результатов вручную через Telegram.

---

## 10. Non-functional requirements

### 10.1 Usability

* Все ключевые сценарии должны проходиться через кнопки и guided actions.
* Свободный текст допустим, но не должен быть единственным способом взаимодействия.

### 10.2 Performance

* Ответы UI-слоя без генерации должны быть быстрыми.
* Генерация меню и replanning могут быть медленнее, но не должны делать UX неуправляемым.

### 10.3 Reliability

* Утвержденное меню не должно теряться.
* Pantry, feedback и active profile должны сохраняться устойчиво.

### 10.4 Extensibility

* Архитектура должна позволять:

  * добавить multi-user позже;
  * добавить reminders;
  * добавить pricing;
  * добавить grocery integrations;
  * добавить web UI.

### 10.5 Observability

Система должна логировать:

* создание профиля;
* генерацию меню;
* подтверждение меню;
* замены блюд;
* генерацию shopping list;
* обновления pantry;
* оценки блюд.

---

## 11. AI responsibilities vs backend responsibilities

## 11.1 AI responsibilities

ИИ отвечает за:

* интерпретацию пользовательских пожеланий;
* генерацию draft меню;
* генерацию альтернатив при replanning;
* адаптацию блюд под запрос;
* генерацию рецептурных описаний;
* генерацию approximate nutrition balance notes.

## 11.2 Backend responsibilities

Backend отвечает за:

* хранение профилей;
* хранение pantry;
* хранение истории и feedback;
* хранение weekly plans;
* дедупликацию ингредиентов;
* shopping list generation logic;
* применение hard constraints;
* определение активного профиля;
* аудит изменений плана.

---

## 12. Data model (MVP draft)

## 12.1 Entities

### users

* `id: UUID`
* `telegram_user_id: int64`
* `created_at: datetime`
* `updated_at: datetime`

### profiles

* `id: UUID`
* `user_id: UUID`
* `name: string`
* `household_size: int`
* `is_active: bool`
* `preferences_json: JSON`
* `constraints_json: JSON`
* `repeatability_mode: enum`
* `created_at: datetime`
* `updated_at: datetime`

### pantry_items

* `id: UUID`
* `profile_id: UUID`
* `ingredient_name: string`
* `quantity_value: float | null`
* `quantity_unit: string | null`
* `stock_level: enum(has, low, empty, unknown)`
* `notes: string | null`
* `updated_at: datetime`

### weekly_plans

* `id: UUID`
* `profile_id: UUID`
* `week_start_date: date`
* `week_end_date: date`
* `status: enum(draft, confirmed, archived)`
* `weekly_notes: string | null`
* `created_at: datetime`
* `updated_at: datetime`

### planned_meals

* `id: UUID`
* `weekly_plan_id: UUID`
* `meal_date: date`
* `meal_slot_label: string | null`
* `meal_type: enum(meal, snack, dessert)`
* `dish_name: string`
* `dish_summary: string`
* `recipe_id: UUID | null`
* `status: enum(planned, replaced, prepared, skipped)`
* `created_at: datetime`
* `updated_at: datetime`

### recipes

* `id: UUID`
* `dish_name: string`
* `summary: string`
* `ingredients_json: JSON`
* `steps_json: JSON`
* `prep_time_minutes: int | null`
* `cook_time_minutes: int | null`
* `tags_json: JSON`
* `nutrition_summary_json: JSON | null`
* `created_at: datetime`
* `updated_at: datetime`

### dish_feedback

* `id: UUID`
* `profile_id: UUID`
* `dish_name: string`
* `recipe_id: UUID | null`
* `rating_value: int | null`
* `repeat_verdict: enum(never_again, rarely_repeat, can_repeat, favorite)`
* `notes: string | null`
* `created_at: datetime`

### shopping_lists

* `id: UUID`
* `weekly_plan_id: UUID`
* `generated_at: datetime`

### shopping_list_items

* `id: UUID`
* `shopping_list_id: UUID`
* `ingredient_name: string`
* `quantity_value: float | null`
* `quantity_unit: string | null`
* `category: string | null`
* `availability_status: enum(need_to_buy, partially_have, already_have)`
* `notes: string | null`

### dish_history

* `id: UUID`
* `profile_id: UUID`
* `dish_name: string`
* `served_on: date`
* `source_plan_id: UUID | null`
* `outcome_status: enum(planned, eaten, skipped, replaced)`

---

## 13. Commands and entry points

## 13.1 Main commands

* `/start` — старт и краткое объяснение
* `/profiles` — список профилей
* `/switch_profile` — сменить активный профиль
* `/setup` — настройка профиля
* `/plan_week` — составить меню
* `/menu` — показать текущее меню недели
* `/today` — блюда на сегодня
* `/replace` — заменить блюдо / день / остаток дня
* `/shopping` — список покупок
* `/pantry` — запасы дома
* `/recipe` — рецепт блюда
* `/rate` — оценить блюда
* `/history` — недавняя история
* `/help` — справка

## 13.2 Preferred interaction mode

Команды нужны как точки входа, но основной UX должен строиться на:

* inline buttons;
* quick replies;
* structured menus;
* коротких guided forms.

---

## 14. UX guidelines

1. Не показывать длинные стены текста.
2. Показ меню по дням должен быть компактным.
3. На каждом блюде должны быть быстрые действия:

   * заменить;
   * рецепт;
   * отметить;
   * оценить.
4. Сегодняшний день должен быть доступен за 1 действие.
5. Replanning должен быть быстрым и локальным.
6. Shopping list должен быть читабельным в Telegram без внешнего UI.
7. Pantry editing должен быть максимально простым, без ощущения инвентаризации склада.

---

## 15. Nutrition logic for MVP

### 15.1 Positioning

Бот не обещает точный подсчет КБЖУ. Он дает приблизительный баланс.

### 15.2 Expected behavior

Система должна:

* избегать экстремально перекошенных дней;
* следить, чтобы в приемах пищи регулярно был источник белка;
* следить за базовым разнообразием;
* учитывать treats без морализаторства;
* не ломать сценарий “фестиваль бургеров”, если пользователь этого хочет;
* уметь строить как indulgent week, так и lighter week.

### 15.3 Internal heuristic

Для MVP допустима эвристика:

* белковый компонент;
* источник углеводов;
* овощи/клетчатка;
* treats в разумном объеме;
* weekly balance важнее per-meal perfection.

---

## 16. Diversity and repeatability logic

### 16.1 Inputs

* история последних 30 дней;
* feedback по блюдам;
* профиль repeatability_mode.

### 16.2 Modes

* `balanced`
* `more_variety`
* `more_repeatability`

### 16.3 Rules

* favorite блюда можно предлагать чаще;
* never_again не предлагать;
* recently served блюда снижать в приоритете;
* похожие блюда тоже считать частично повторяющимися;
* diversity mode не должен ломать бытовую практичность.

---

## 17. Pantry logic for MVP

### 17.1 Supported states

* есть;
* мало;
* меньше X грамм / мл / штук;
* нет.

### 17.2 Expected behavior

* При планировании бот должен уметь использовать pantry как soft signal.
* При shopping generation pantry должен влиять на availability status.
* После приготовления пользователь должен иметь возможность вручную:

  * списать использованное;
  * отметить, что продукт закончился;
  * скорректировать остатки.

### 17.3 Explicit limitation

MVP не ведет точный автоматический учет расхода по всем ингредиентам.

---

## 18. Edge cases

Система должна учитывать:

* пропуск одного или нескольких приемов пищи;
* спонтанное желание заменить весь день;
* частично отсутствующие ингредиенты;
* наличие только части нужного продукта;
* профили с radically different weeks;
* очень свободные запросы пользователя;
* просьбу “что-то нормальное из того, что есть дома”;
* наличие treats/deserts в плане;
* неполное заполнение pantry;
* отсутствие feedback на многих блюдах.

---

## 19. Metrics of MVP success

### 19.1 Product metrics

* Доля пользователей, завершивших onboarding.
* Доля пользователей, составивших хотя бы один weekly plan.
* Доля weekly plans, дошедших до confirmed.
* Частота использования `/today`.
* Частота использования `/shopping`.
* Частота replanning.
* Доля блюд с feedback.
* Повторное weekly usage через 7 дней.

### 19.2 Quality metrics

* Средняя удовлетворенность weekly plan.
* Доля блюд, помеченных как favorite / can_repeat.
* Доля блюд, помеченных never_again.
* Частота ручных замен после генерации.
* Частота использования pantry в planning flow.

---

## 20. Technical architecture (MVP)

## 20.1 Recommended stack

* **Python**
* **FastAPI**
* **Telegram bot framework:** `aiogram`
* **PostgreSQL**
* **SQLAlchemy`or`SQLModel`
* **Redis** for state/cache/future scaling
* **LLM provider API** for menu/reasoning/generation

## 20.2 Services

### Bot layer

* Telegram updates
* command routing
* button callbacks
* session handling

### Application layer

* profile management
* planning orchestration
* replanning orchestration
* pantry operations
* shopping list generation
* feedback processing

### AI layer

* prompt templates
* menu generation
* dish replacement
* recipe generation
* normalization of user wishes

### Persistence layer

* PostgreSQL models
* repositories
* query services

## 20.3 Redis rationale

Для MVP Redis можно считать optional-but-recommended:

* FSM state;
* temporary generation sessions;
* caching recent planning contexts;
* scaling readiness.

Если библиотека позволяет обойтись без Redis на старте, архитектура должна все равно позволять добавить его без перестройки core domain.

---

## 21. Risks

### 21.1 Product risks

* Слишком свободный conversational UX становится неудобным.
* Пользователь ожидает слишком точный nutrition advice.
* Shopping list будет раздражать, если ингредиенты плохо нормализуются.
* Pantry станет тяжелым для ведения, если слишком усложнить модель.

### 21.2 Technical risks

* LLM может выдавать странные рецепты или несогласованные ингредиенты.
* Сложно поддерживать consistency между recipe, pantry и shopping list.
* Replanning может ломать общую недельную логику, если не делать пересчет аккуратно.

### 21.3 UX risks

* Слишком длинный onboarding.
* Слишком много ручных вопросов перед первой ценностью.
* Перегрузка пользователя деталями вместо быстрых решений.

---

## 22. MVP release criteria

MVP считается готовым, если:

1. Пользователь может создать профиль.
2. Пользователь может составить weekly menu.
3. Пользователь может заменить отдельные блюда.
4. Пользователь может посмотреть план на сегодня.
5. Пользователь может получить shopping list.
6. Пользователь может вести pantry в упрощенном виде.
7. Пользователь может поставить feedback блюдам.
8. Система использует history + pantry + preferences при следующем планировании.

---

## 23. Future roadmap (post-MVP)

### Phase 2

* shared household with multiple Telegram accounts
* weekly reminders
* better pantry suggestions
* recipe favorites collection
* export/share weekly plan

### Phase 3

* grocery/store integrations
* budget-aware planning
* batch cooking mode
* leftovers logic
* better nutrition knowledge base

### Phase 4

* web/mobile companion UI
* richer analytics
* seasonal suggestions
* household collaboration workflows

---

## 24. Open questions

1. Нужен ли явный weekly reminder в определенный день недели?
2. Нужен ли режим “собери только на 3 дня”, если неделя пока не определена?
3. Нужно ли сохранять шаблоны недель: “ленивая неделя”, “детокс неделя”, “comfort week”?
4. Нужно ли отдельное действие “используй продукты, которые скоро закончатся” как post-MVP?
5. Нужен ли режим “только список идей без полного плана”?
6. Нужно ли разделять “готовить” и “купить” как отдельные Telegram сообщения для удобной пересылки?

---

## 25. Final product definition

`Telegram Meal Planner Bot` в MVP — это AI-assisted бытовой планировщик питания на неделю, который:

* работает внутри Telegram;
* поддерживает несколько профилей в одном аккаунте;
* помогает собрать меню на неделю;
* учитывает предпочтения, историю и продукты дома;
* умеет быстро менять план;
* выдает список покупок и рецепты;
* запоминает, что понравилось, а что нет.

Он не пытается быть диетологом или chef-grade системой. Его задача — делать недельное планирование еды простым, гибким и реально полезным в повседневной жизни.
