CREATE DATABASE IF NOT EXISTS code_platform
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATION utf8mb4_unicode_ci;

USE code_platform;

CREATE TABLE users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('user','admin') NOT NULL DEFAULT 'user',
  status ENUM('active','blocked','deleted') NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_settings (
  user_id BIGINT PRIMARY KEY,
  preferred_language VARCHAR(30) NOT NULL DEFAULT 'python',
  preferred_difficulty ENUM('easy','medium','hard') NOT NULL DEFAULT 'medium',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE user_sessions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  refresh_token_hash VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id);
CREATE INDEX ix_user_sessions_refresh_token_hash ON user_sessions (refresh_token_hash);
CREATE INDEX ix_user_sessions_active_lookup ON user_sessions (refresh_token_hash, revoked_at, expires_at);

CREATE TABLE problems (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  kind ENUM('coding','code_block','auditor','context_inference','refactoring_choice','code_blame') NOT NULL,
  title VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  difficulty ENUM('easy','medium','hard') NOT NULL,
  language VARCHAR(30) NOT NULL,
  starter_code TEXT,
  options JSON,
  answer_index INT,
  reference_solution TEXT,
  is_published BOOLEAN NOT NULL DEFAULT 1,
  created_by BIGINT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX ix_problems_created_by ON problems (created_by);

CREATE TABLE submissions (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  problem_id BIGINT NOT NULL,
  language VARCHAR(30) NOT NULL,
  code TEXT NOT NULL,
  status ENUM('pending','processing','passed','failed','error') NOT NULL,
  score INT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);
CREATE INDEX ix_submissions_created_at ON submissions (created_at);
CREATE INDEX ix_submissions_problem_id ON submissions (problem_id);
CREATE INDEX ix_submissions_user_id ON submissions (user_id);

CREATE TABLE ai_analyses (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  submission_id BIGINT,
  analysis_type ENUM('error','review','hint','explain') NOT NULL,
  result_summary TEXT NOT NULL,
  result_detail TEXT,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (submission_id) REFERENCES submissions(id) ON DELETE SET NULL
);
CREATE INDEX ix_ai_analyses_created_at ON ai_analyses (created_at);
CREATE INDEX ix_ai_analyses_submission_id ON ai_analyses (submission_id);
CREATE INDEX ix_ai_analyses_user_id ON ai_analyses (user_id);

CREATE TABLE user_problem_stats (
  user_id BIGINT NOT NULL,
  problem_id BIGINT NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  best_status ENUM('pending','passed','failed','error'),
  best_score INT,
  last_submitted_at DATETIME,
  wrong_answer_types JSON,
  PRIMARY KEY (user_id, problem_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE CASCADE
);

CREATE TABLE reports (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  report_type ENUM('weekly','monthly','milestone') NOT NULL,
  period_start DATETIME,
  period_end DATETIME,
  milestone_problem_count INT,
  title VARCHAR(200) NOT NULL,
  summary TEXT NOT NULL,
  strengths JSON,
  weaknesses JSON,
  recommendations JSON,
  stats JSON NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE INDEX ix_reports_created_at ON reports (created_at);
CREATE INDEX ix_reports_user_id ON reports (user_id);
