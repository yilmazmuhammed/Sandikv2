CREATE TABLE "Sandik" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "contribution_amount" DECIMAL(12, 2) NOT NULL,
  "is_active" BOOLEAN NOT NULL,
  "date_of_opening" DATE NOT NULL,
  "detail" VARCHAR(1000) NOT NULL,
  "type" INTEGER NOT NULL
);

CREATE TABLE "SandikAuthorityType" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "name" TEXT NOT NULL,
  "is_admin" BOOLEAN NOT NULL,
  "can_read" BOOLEAN NOT NULL,
  "can_write" BOOLEAN NOT NULL,
  "sandik_ref" INTEGER NOT NULL REFERENCES "Sandik" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_sandikauthoritytype__sandik_ref" ON "SandikAuthorityType" ("sandik_ref");

CREATE TABLE "SandikRule" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "type" INTEGER NOT NULL,
  "order" INTEGER NOT NULL,
  "sandik_ref" INTEGER NOT NULL REFERENCES "Sandik" ("id") ON DELETE CASCADE,
  "condition_formula" TEXT NOT NULL,
  "value_formula" TEXT NOT NULL
);

CREATE INDEX "idx_sandikrule__sandik_ref" ON "SandikRule" ("sandik_ref");

CREATE TABLE "SmsPackage" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "text" TEXT NOT NULL,
  "header" TEXT NOT NULL,
  "type" INTEGER NOT NULL,
  "status" INTEGER NOT NULL,
  "external_api_task_id" TEXT NOT NULL,
  "sandik_ref" INTEGER REFERENCES "Sandik" ("id") ON DELETE SET NULL
);

CREATE INDEX "idx_smspackage__sandik_ref" ON "SmsPackage" ("sandik_ref");

CREATE TABLE "WebUser" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "email_address" TEXT UNIQUE NOT NULL,
  "password_hash" TEXT NOT NULL,
  "tc" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "surname" TEXT NOT NULL,
  "registration_time" DATETIME NOT NULL,
  "is_active_" BOOLEAN NOT NULL,
  "telegram_chat_id" INTEGER,
  "phone_number" TEXT NOT NULL
);

CREATE TABLE "BankAccount" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "title" TEXT NOT NULL,
  "holder" TEXT NOT NULL,
  "iban" TEXT NOT NULL,
  "web_user_ref" INTEGER REFERENCES "WebUser" ("id") ON DELETE SET NULL,
  "sandik_ref" INTEGER REFERENCES "Sandik" ("id") ON DELETE SET NULL,
  "is_primary" BOOLEAN NOT NULL
);

CREATE INDEX "idx_bankaccount__sandik_ref" ON "BankAccount" ("sandik_ref");

CREATE INDEX "idx_bankaccount__web_user_ref" ON "BankAccount" ("web_user_ref");

CREATE TABLE "Member" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "web_user_ref" INTEGER REFERENCES "WebUser" ("id") ON DELETE SET NULL,
  "sandik_ref" INTEGER NOT NULL REFERENCES "Sandik" ("id") ON DELETE CASCADE,
  "date_of_membership" DATE NOT NULL,
  "contribution_amount" DECIMAL(12, 2) NOT NULL,
  "detail" VARCHAR(1000) NOT NULL,
  "is_active" BOOLEAN NOT NULL
);

CREATE INDEX "idx_member__sandik_ref" ON "Member" ("sandik_ref");

CREATE INDEX "idx_member__web_user_ref" ON "Member" ("web_user_ref");

CREATE TABLE "MoneyTransaction" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "date" DATE NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "detail" VARCHAR(1000) NOT NULL,
  "type" INTEGER NOT NULL,
  "is_fully_distributed" BOOLEAN NOT NULL,
  "creation_type" INTEGER NOT NULL,
  "member_ref" INTEGER NOT NULL REFERENCES "Member" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_moneytransaction__member_ref" ON "MoneyTransaction" ("member_ref");

CREATE TABLE "BankTransaction" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "time" DATETIME NOT NULL,
  "description" TEXT NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "tref_id" TEXT NOT NULL,
  "bank_account_ref" INTEGER NOT NULL REFERENCES "BankAccount" ("id") ON DELETE CASCADE,
  "money_transaction_ref" INTEGER REFERENCES "MoneyTransaction" ("id") ON DELETE SET NULL
);

CREATE INDEX "idx_banktransaction__bank_account_ref" ON "BankTransaction" ("bank_account_ref");

CREATE INDEX "idx_banktransaction__money_transaction_ref" ON "BankTransaction" ("money_transaction_ref");

CREATE TABLE "Notification" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "web_user_ref" INTEGER REFERENCES "WebUser" ("id") ON DELETE SET NULL,
  "title" TEXT NOT NULL,
  "text" TEXT NOT NULL,
  "url" TEXT NOT NULL,
  "creation_time" DATETIME NOT NULL,
  "reading_time" DATETIME
);

CREATE INDEX "idx_notification__web_user_ref" ON "Notification" ("web_user_ref");

CREATE TABLE "SandikAuthorityType_WebUser" (
  "sandikauthoritytype" INTEGER NOT NULL REFERENCES "SandikAuthorityType" ("id"),
  "webuser" INTEGER NOT NULL REFERENCES "WebUser" ("id"),
  PRIMARY KEY ("sandikauthoritytype", "webuser")
);

CREATE INDEX "idx_sandikauthoritytype_webuser" ON "SandikAuthorityType_WebUser" ("webuser");

CREATE TABLE "Sandik_WebUser" (
  "sandik" INTEGER NOT NULL REFERENCES "Sandik" ("id"),
  "webuser" INTEGER NOT NULL REFERENCES "WebUser" ("id"),
  PRIMARY KEY ("sandik", "webuser")
);

CREATE INDEX "idx_sandik_webuser" ON "Sandik_WebUser" ("webuser");

CREATE TABLE "Share" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "member_ref" INTEGER NOT NULL REFERENCES "Member" ("id") ON DELETE CASCADE,
  "share_order_of_member" INTEGER NOT NULL,
  "date_of_opening" DATE NOT NULL,
  "is_active" BOOLEAN NOT NULL
);

CREATE INDEX "idx_share__member_ref" ON "Share" ("member_ref");

CREATE TABLE "Contribution" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL(12, 2) NOT NULL,
  "term" TEXT NOT NULL,
  "is_fully_paid" BOOLEAN NOT NULL,
  "share_ref" INTEGER NOT NULL REFERENCES "Share" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_contribution__share_ref" ON "Contribution" ("share_ref");

CREATE TABLE "SmsPackage_WebUser" (
  "smspackage" INTEGER NOT NULL REFERENCES "SmsPackage" ("id"),
  "webuser" INTEGER NOT NULL REFERENCES "WebUser" ("id"),
  PRIMARY KEY ("smspackage", "webuser")
);

CREATE INDEX "idx_smspackage_webuser" ON "SmsPackage_WebUser" ("webuser");

CREATE TABLE "TrustRelationship" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "status" INTEGER NOT NULL,
  "time" DATETIME NOT NULL,
  "requester_member_ref" INTEGER NOT NULL REFERENCES "Member" ("id") ON DELETE CASCADE,
  "receiver_member_ref" INTEGER NOT NULL REFERENCES "Member" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_trustrelationship__receiver_member_ref" ON "TrustRelationship" ("receiver_member_ref");

CREATE INDEX "idx_trustrelationship__requester_member_ref" ON "TrustRelationship" ("requester_member_ref");

CREATE TABLE "WebsiteTransaction" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "payer" TEXT NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "type" INTEGER NOT NULL,
  "category" TEXT NOT NULL,
  "web_user_ref" INTEGER REFERENCES "WebUser" ("id") ON DELETE SET NULL,
  "date" DATE NOT NULL,
  "detail" TEXT NOT NULL
);

CREATE INDEX "idx_websitetransaction__web_user_ref" ON "WebsiteTransaction" ("web_user_ref");

CREATE TABLE "SubReceipt" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL(12, 2) NOT NULL,
  "is_auto" BOOLEAN NOT NULL,
  "contribution_ref" INTEGER REFERENCES "Contribution" ("id") ON DELETE SET NULL,
  "installment_ref" INTEGER REFERENCES "Installment" ("id") ON DELETE SET NULL,
  "money_transaction_ref" INTEGER NOT NULL REFERENCES "MoneyTransaction" ("id") ON DELETE CASCADE,
  "share_ref" INTEGER REFERENCES "Share" ("id") ON DELETE SET NULL,
  "creation_time" DATETIME NOT NULL
);

CREATE INDEX "idx_subreceipt__contribution_ref" ON "SubReceipt" ("contribution_ref");

CREATE INDEX "idx_subreceipt__installment_ref" ON "SubReceipt" ("installment_ref");

CREATE INDEX "idx_subreceipt__money_transaction_ref" ON "SubReceipt" ("money_transaction_ref");

CREATE INDEX "idx_subreceipt__share_ref" ON "SubReceipt" ("share_ref");

CREATE TABLE "Retracted" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL(12, 2) NOT NULL,
  "expense_sub_receipt_ref" INTEGER NOT NULL REFERENCES "SubReceipt" ("id"),
  "revenue_sub_receipt_ref" INTEGER NOT NULL REFERENCES "SubReceipt" ("id")
);

CREATE INDEX "idx_retracted__expense_sub_receipt_ref" ON "Retracted" ("expense_sub_receipt_ref");

CREATE INDEX "idx_retracted__revenue_sub_receipt_ref" ON "Retracted" ("revenue_sub_receipt_ref");

CREATE TABLE "PieceOfDebt" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "member_ref" INTEGER NOT NULL REFERENCES "Member" ("id") ON DELETE CASCADE,
  "debt_ref" INTEGER NOT NULL REFERENCES "Debt" ("id") ON DELETE CASCADE,
  "amount" DECIMAL(12, 2) NOT NULL,
  "paid_amount" DECIMAL(12, 2) NOT NULL
);

CREATE INDEX "idx_pieceofdebt__debt_ref" ON "PieceOfDebt" ("debt_ref");

CREATE INDEX "idx_pieceofdebt__member_ref" ON "PieceOfDebt" ("member_ref");

CREATE TABLE "Log" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "web_user_ref" INTEGER NOT NULL REFERENCES "WebUser" ("id") ON DELETE CASCADE,
  "time" DATETIME NOT NULL,
  "type" INTEGER NOT NULL,
  "special_type" TEXT NOT NULL,
  "detail" VARCHAR(1000) NOT NULL,
  "logged_bank_account_ref" INTEGER REFERENCES "BankAccount" ("id") ON DELETE SET NULL,
  "logged_retracted_ref" INTEGER REFERENCES "Retracted" ("id") ON DELETE SET NULL,
  "logged_contribution_ref" INTEGER REFERENCES "Contribution" ("id") ON DELETE SET NULL,
  "logged_installment_ref" INTEGER REFERENCES "Installment" ("id") ON DELETE SET NULL,
  "logged_debt_ref" INTEGER REFERENCES "Debt" ("id") ON DELETE SET NULL,
  "logged_sub_receipt_ref" INTEGER REFERENCES "SubReceipt" ("id") ON DELETE SET NULL,
  "logged_piece_of_debt_ref" INTEGER REFERENCES "PieceOfDebt" ("id") ON DELETE SET NULL,
  "logged_bank_transaction_ref" INTEGER REFERENCES "BankTransaction" ("id") ON DELETE SET NULL,
  "logged_money_transaction_ref" INTEGER REFERENCES "MoneyTransaction" ("id") ON DELETE SET NULL,
  "logged_share_ref" INTEGER REFERENCES "Share" ("id") ON DELETE SET NULL,
  "logged_member_ref" INTEGER REFERENCES "Member" ("id") ON DELETE SET NULL,
  "logged_sandik_ref" INTEGER REFERENCES "Sandik" ("id") ON DELETE SET NULL,
  "logged_website_transaction_ref" INTEGER REFERENCES "WebsiteTransaction" ("id") ON DELETE SET NULL,
  "logged_sms_package_ref" INTEGER REFERENCES "SmsPackage" ("id") ON DELETE SET NULL,
  "logged_web_user_ref" INTEGER REFERENCES "WebUser" ("id") ON DELETE SET NULL,
  "logged_sandik_authority_type_ref" INTEGER REFERENCES "SandikAuthorityType" ("id") ON DELETE SET NULL,
  "logged_sandik_rule_ref" INTEGER REFERENCES "SandikRule" ("id") ON DELETE SET NULL,
  "logged_trust_relationship_ref" INTEGER REFERENCES "TrustRelationship" ("id") ON DELETE SET NULL
);

CREATE INDEX "idx_log__logged_bank_account_ref" ON "Log" ("logged_bank_account_ref");

CREATE INDEX "idx_log__logged_bank_transaction_ref" ON "Log" ("logged_bank_transaction_ref");

CREATE INDEX "idx_log__logged_contribution_ref" ON "Log" ("logged_contribution_ref");

CREATE INDEX "idx_log__logged_debt_ref" ON "Log" ("logged_debt_ref");

CREATE INDEX "idx_log__logged_installment_ref" ON "Log" ("logged_installment_ref");

CREATE INDEX "idx_log__logged_member_ref" ON "Log" ("logged_member_ref");

CREATE INDEX "idx_log__logged_money_transaction_ref" ON "Log" ("logged_money_transaction_ref");

CREATE INDEX "idx_log__logged_piece_of_debt_ref" ON "Log" ("logged_piece_of_debt_ref");

CREATE INDEX "idx_log__logged_retracted_ref" ON "Log" ("logged_retracted_ref");

CREATE INDEX "idx_log__logged_sandik_authority_type_ref" ON "Log" ("logged_sandik_authority_type_ref");

CREATE INDEX "idx_log__logged_sandik_ref" ON "Log" ("logged_sandik_ref");

CREATE INDEX "idx_log__logged_sandik_rule_ref" ON "Log" ("logged_sandik_rule_ref");

CREATE INDEX "idx_log__logged_share_ref" ON "Log" ("logged_share_ref");

CREATE INDEX "idx_log__logged_sms_package_ref" ON "Log" ("logged_sms_package_ref");

CREATE INDEX "idx_log__logged_sub_receipt_ref" ON "Log" ("logged_sub_receipt_ref");

CREATE INDEX "idx_log__logged_trust_relationship_ref" ON "Log" ("logged_trust_relationship_ref");

CREATE INDEX "idx_log__logged_web_user_ref" ON "Log" ("logged_web_user_ref");

CREATE INDEX "idx_log__logged_website_transaction_ref" ON "Log" ("logged_website_transaction_ref");

CREATE INDEX "idx_log__web_user_ref" ON "Log" ("web_user_ref");

CREATE TABLE "Installment" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL(12, 2) NOT NULL,
  "term" TEXT NOT NULL,
  "is_fully_paid" BOOLEAN NOT NULL,
  "debt_ref" INTEGER NOT NULL REFERENCES "Debt" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_installment__debt_ref" ON "Installment" ("debt_ref");

CREATE TABLE "Debt" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "amount" DECIMAL(12, 2) NOT NULL,
  "number_of_installment" INTEGER NOT NULL,
  "starting_term" TEXT NOT NULL,
  "due_term" TEXT NOT NULL,
  "sub_receipt_ref" INTEGER NOT NULL REFERENCES "SubReceipt" ("id"),
  "share_ref" INTEGER NOT NULL REFERENCES "Share" ("id") ON DELETE CASCADE
);

CREATE INDEX "idx_debt__share_ref" ON "Debt" ("share_ref");

CREATE INDEX "idx_debt__sub_receipt_ref" ON "Debt" ("sub_receipt_ref")