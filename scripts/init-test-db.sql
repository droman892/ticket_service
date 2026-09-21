-- Runs once, only when the Postgres data volume is first created (see
-- docker-compose.yml). Gives tests their own database so they never touch
-- dev data, without needing a second container.
CREATE DATABASE ticket_service_test OWNER ticket_service;
