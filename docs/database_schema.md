# Схема базы данных Mediary
Автор: учебного проекта

| Сущность | Поля |
|---|---|
| Medication | id PK; owner_id FK → auth_user.id; name; purpose; dosage; frequency; as_needed; daily_doses; scheduled_times JSON; start_date NULL; end_date NULL |
| MedicationIntake | id PK; medication_id FK; date; slot; scheduled_time NULL; taken; taken_at NULL; is_extra; reason |
| HealthEntry | id PK; owner_id FK → auth_user.id; date; mood; condition; symptoms; pain_intensity; note NULL |

У пользователя (auth_user) много препаратов и записей самочувствия. Уникальна пара (owner_id, date) дневника.

Связь: Medication 1 → N MedicationIntake. HealthEntry не зависит от препарата.

Ограничения: ежедневное количество 1–12; slot ≥ 1; боль 0–10; UNIQUE(medication_id, date, slot); UNIQUE(medication_id, date, scheduled_time). NULL позволяет нескольким приёмам быть без времени. taken_at допускается только при taken=True. У регулярного препарата обязательны даты, end_date ≥ start_date; у режима «Иногда» даты не требуются. Удаление препарата удаляет связанные приёмы (CASCADE).

Серверные формы дополнительно проверяют обязательные поля, корректность и уникальность времён, будущие фактические даты и даты дневника. `reason` — необязательная причина конкретного приёма, до 300 символов. `is_extra` отделяет дополнительную запись от ежедневного плана. Внутренний признак `as_needed=True` соответствует режиму «Иногда».
