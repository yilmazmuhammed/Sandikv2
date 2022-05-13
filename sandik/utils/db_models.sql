CREATE TABLE "sandik" (
  "id" SERIAL PRIMARY KEY,
  "name" TEXT NOT NULL,
  "contribution_amount" DECIMAL(12, 2) NOT NULL,
  "is_active" BOOLEAN NOT NULL,
  "date_of_opening" DATE NOT NULL,
  "detail" TEXT NOT NULL
);

CREATE TABLE "sandikauthoritytype" (
  "id" SERIAL PRIMARY KEY,
  "name" TEXT NOT NULL,
  "is_admin" BOOLEAN NOT NULL,
  "can_read" BOOLEAN NOT NULL,
  "can_write" BOOLEAN NOT NULL,
  "sandik_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_sandikauthoritytype__sandik_ref" ON "sandikauthoritytype" ("sandik_ref");

ALTER TABLE "sandikauthoritytype" ADD CONSTRAINT "fk_sandikauthoritytype__sandik_ref" FOREIGN KEY ("sandik_ref") REFERENCES "sandik" ("id") ON DELETE CASCADE;

CREATE TABLE "smspackage" (
  "id" SERIAL PRIMARY KEY,
  "text" TEXT NOT NULL,
  "header" TEXT NOT NULL,
  "type" INTEGER NOT NULL,
  "status" INTEGER NOT NULL,
  "external_api_task_id" TEXT NOT NULL,
  "sandik_ref" INTEGER
);

CREATE INDEX "idx_smspackage__sandik_ref" ON "smspackage" ("sandik_ref");

ALTER TABLE "smspackage" ADD CONSTRAINT "fk_smspackage__sandik_ref" FOREIGN KEY ("sandik_ref") REFERENCES "sandik" ("id") ON DELETE SET NULL;

CREATE TABLE "webuser" (
  "id" SERIAL PRIMARY KEY,
  "email_address" TEXT UNIQUE NOT NULL,
  "password_hash" TEXT NOT NULL,
  "tc" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "surname" TEXT NOT NULL,
  "registration_time" TIMESTAMP NOT NULL,
  "is_active_" BOOLEAN NOT NULL,
  "telegram_chat_id" INTEGER,
  "phone_number" TEXT NOT NULL
);

CREATE TABLE "bankaccount" (
  "id" SERIAL PRIMARY KEY,
  "title" TEXT NOT NULL,
  "holder" TEXT NOT NULL,
  "iban" TEXT NOT NULL,
  "web_user_ref" INTEGER,
  "sandik_ref" INTEGER,
  "is_primary" BOOLEAN NOT NULL
);

CREATE INDEX "idx_bankaccount__sandik_ref" ON "bankaccount" ("sandik_ref");

CREATE INDEX "idx_bankaccount__web_user_ref" ON "bankaccount" ("web_user_ref");

ALTER TABLE "bankaccount" ADD CONSTRAINT "fk_bankaccount__sandik_ref" FOREIGN KEY ("sandik_ref") REFERENCES "sandik" ("id") ON DELETE SET NULL;

ALTER TABLE "bankaccount" ADD CONSTRAINT "fk_bankaccount__web_user_ref" FOREIGN KEY ("web_user_ref") REFERENCES "webuser" ("id") ON DELETE SET NULL;

CREATE TABLE "member" (
  "id" SERIAL PRIMARY KEY,
  "web_user_ref" INTEGER,
  "sandik_ref" INTEGER NOT NULL,
  "date_of_membership" DATE NOT NULL,
  "contribution_amount" DECIMAL(12, 2) NOT NULL,
  "detail" TEXT NOT NULL,
  "is_active" BOOLEAN NOT NULL,
  "balance" DECIMAL(12, 2) NOT NULL
);

CREATE INDEX "idx_member__sandik_ref" ON "member" ("sandik_ref");

CREATE INDEX "idx_member__web_user_ref" ON "member" ("web_user_ref");

ALTER TABLE "member" ADD CONSTRAINT "fk_member__sandik_ref" FOREIGN KEY ("sandik_ref") REFERENCES "sandik" ("id") ON DELETE CASCADE;

ALTER TABLE "member" ADD CONSTRAINT "fk_member__web_user_ref" FOREIGN KEY ("web_user_ref") REFERENCES "webuser" ("id") ON DELETE SET NULL;

CREATE TABLE "moneytransaction" (
  "id" SERIAL PRIMARY KEY,
  "date" DATE NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "detail" TEXT NOT NULL,
  "type" INTEGER NOT NULL,
  "is_fully_distributed" BOOLEAN NOT NULL,
  "creation_type" INTEGER NOT NULL,
  "member_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_moneytransaction__member_ref" ON "moneytransaction" ("member_ref");

ALTER TABLE "moneytransaction" ADD CONSTRAINT "fk_moneytransaction__member_ref" FOREIGN KEY ("member_ref") REFERENCES "member" ("id") ON DELETE CASCADE;

CREATE TABLE "banktransaction" (
  "id" SERIAL PRIMARY KEY,
  "time" TIMESTAMP NOT NULL,
  "description" TEXT NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "tref_id" TEXT NOT NULL,
  "bank_account_ref" INTEGER NOT NULL,
  "money_transaction_ref" INTEGER
);

CREATE INDEX "idx_banktransaction__bank_account_ref" ON "banktransaction" ("bank_account_ref");

CREATE INDEX "idx_banktransaction__money_transaction_ref" ON "banktransaction" ("money_transaction_ref");

ALTER TABLE "banktransaction" ADD CONSTRAINT "fk_banktransaction__bank_account_ref" FOREIGN KEY ("bank_account_ref") REFERENCES "bankaccount" ("id") ON DELETE CASCADE;

ALTER TABLE "banktransaction" ADD CONSTRAINT "fk_banktransaction__money_transaction_ref" FOREIGN KEY ("money_transaction_ref") REFERENCES "moneytransaction" ("id") ON DELETE SET NULL;

CREATE TABLE "notification" (
  "id" SERIAL PRIMARY KEY,
  "web_user_ref" INTEGER,
  "title" TEXT NOT NULL,
  "text" TEXT NOT NULL,
  "url" TEXT NOT NULL,
  "creation_time" TIMESTAMP NOT NULL,
  "reading_time" TIMESTAMP
);

CREATE INDEX "idx_notification__web_user_ref" ON "notification" ("web_user_ref");

ALTER TABLE "notification" ADD CONSTRAINT "fk_notification__web_user_ref" FOREIGN KEY ("web_user_ref") REFERENCES "webuser" ("id") ON DELETE SET NULL;

CREATE TABLE "sandik_webuser" (
  "sandik" INTEGER NOT NULL,
  "webuser" INTEGER NOT NULL,
  PRIMARY KEY ("sandik", "webuser")
);

CREATE INDEX "idx_sandik_webuser" ON "sandik_webuser" ("webuser");

ALTER TABLE "sandik_webuser" ADD CONSTRAINT "fk_sandik_webuser__sandik" FOREIGN KEY ("sandik") REFERENCES "sandik" ("id");

ALTER TABLE "sandik_webuser" ADD CONSTRAINT "fk_sandik_webuser__webuser" FOREIGN KEY ("webuser") REFERENCES "webuser" ("id");

CREATE TABLE "sandikauthoritytype_webuser" (
  "sandikauthoritytype" INTEGER NOT NULL,
  "webuser" INTEGER NOT NULL,
  PRIMARY KEY ("sandikauthoritytype", "webuser")
);

CREATE INDEX "idx_sandikauthoritytype_webuser" ON "sandikauthoritytype_webuser" ("webuser");

ALTER TABLE "sandikauthoritytype_webuser" ADD CONSTRAINT "fk_sandikauthoritytype_webuser__sandikauthoritytype" FOREIGN KEY ("sandikauthoritytype") REFERENCES "sandikauthoritytype" ("id");

ALTER TABLE "sandikauthoritytype_webuser" ADD CONSTRAINT "fk_sandikauthoritytype_webuser__webuser" FOREIGN KEY ("webuser") REFERENCES "webuser" ("id");

CREATE TABLE "share" (
  "id" SERIAL PRIMARY KEY,
  "member_ref" INTEGER NOT NULL,
  "share_order_of_member" INTEGER NOT NULL,
  "date_of_opening" DATE NOT NULL,
  "is_active" BOOLEAN NOT NULL
);

CREATE INDEX "idx_share__member_ref" ON "share" ("member_ref");

ALTER TABLE "share" ADD CONSTRAINT "fk_share__member_ref" FOREIGN KEY ("member_ref") REFERENCES "member" ("id") ON DELETE CASCADE;

CREATE TABLE "contribution" (
  "id" SERIAL PRIMARY KEY,
  "amount" DECIMAL(12, 2) NOT NULL,
  "term" TEXT NOT NULL,
  "is_fully_paid" BOOLEAN NOT NULL,
  "share_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_contribution__share_ref" ON "contribution" ("share_ref");

ALTER TABLE "contribution" ADD CONSTRAINT "fk_contribution__share_ref" FOREIGN KEY ("share_ref") REFERENCES "share" ("id") ON DELETE CASCADE;

CREATE TABLE "smspackage_webuser" (
  "smspackage" INTEGER NOT NULL,
  "webuser" INTEGER NOT NULL,
  PRIMARY KEY ("smspackage", "webuser")
);

CREATE INDEX "idx_smspackage_webuser" ON "smspackage_webuser" ("webuser");

ALTER TABLE "smspackage_webuser" ADD CONSTRAINT "fk_smspackage_webuser__smspackage" FOREIGN KEY ("smspackage") REFERENCES "smspackage" ("id");

ALTER TABLE "smspackage_webuser" ADD CONSTRAINT "fk_smspackage_webuser__webuser" FOREIGN KEY ("webuser") REFERENCES "webuser" ("id");

CREATE TABLE "trustrelationship" (
  "id" SERIAL PRIMARY KEY,
  "status" INTEGER NOT NULL,
  "time" TIMESTAMP NOT NULL,
  "requester_member_ref" INTEGER NOT NULL,
  "receiver_member_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_trustrelationship__receiver_member_ref" ON "trustrelationship" ("receiver_member_ref");

CREATE INDEX "idx_trustrelationship__requester_member_ref" ON "trustrelationship" ("requester_member_ref");

ALTER TABLE "trustrelationship" ADD CONSTRAINT "fk_trustrelationship__receiver_member_ref" FOREIGN KEY ("receiver_member_ref") REFERENCES "member" ("id") ON DELETE CASCADE;

ALTER TABLE "trustrelationship" ADD CONSTRAINT "fk_trustrelationship__requester_member_ref" FOREIGN KEY ("requester_member_ref") REFERENCES "member" ("id") ON DELETE CASCADE;

CREATE TABLE "subreceipt" (
  "id" SERIAL PRIMARY KEY,
  "amount" DECIMAL(12, 2) NOT NULL,
  "is_auto" BOOLEAN NOT NULL,
  "contribution_ref" INTEGER,
  "installment_ref" INTEGER,
  "money_transaction_ref" INTEGER NOT NULL,
  "share_ref" INTEGER,
  "creation_time" TIMESTAMP NOT NULL
);

CREATE INDEX "idx_subreceipt__contribution_ref" ON "subreceipt" ("contribution_ref");

CREATE INDEX "idx_subreceipt__installment_ref" ON "subreceipt" ("installment_ref");

CREATE INDEX "idx_subreceipt__money_transaction_ref" ON "subreceipt" ("money_transaction_ref");

CREATE INDEX "idx_subreceipt__share_ref" ON "subreceipt" ("share_ref");

ALTER TABLE "subreceipt" ADD CONSTRAINT "fk_subreceipt__contribution_ref" FOREIGN KEY ("contribution_ref") REFERENCES "contribution" ("id") ON DELETE SET NULL;

ALTER TABLE "subreceipt" ADD CONSTRAINT "fk_subreceipt__money_transaction_ref" FOREIGN KEY ("money_transaction_ref") REFERENCES "moneytransaction" ("id") ON DELETE CASCADE;

ALTER TABLE "subreceipt" ADD CONSTRAINT "fk_subreceipt__share_ref" FOREIGN KEY ("share_ref") REFERENCES "share" ("id") ON DELETE SET NULL;

CREATE TABLE "retracted" (
  "id" SERIAL PRIMARY KEY,
  "amount" DECIMAL(12, 2) NOT NULL,
  "expense_sub_receipt_ref" INTEGER NOT NULL,
  "revenue_sub_receipt_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_retracted__expense_sub_receipt_ref" ON "retracted" ("expense_sub_receipt_ref");

CREATE INDEX "idx_retracted__revenue_sub_receipt_ref" ON "retracted" ("revenue_sub_receipt_ref");

ALTER TABLE "retracted" ADD CONSTRAINT "fk_retracted__expense_sub_receipt_ref" FOREIGN KEY ("expense_sub_receipt_ref") REFERENCES "subreceipt" ("id");

ALTER TABLE "retracted" ADD CONSTRAINT "fk_retracted__revenue_sub_receipt_ref" FOREIGN KEY ("revenue_sub_receipt_ref") REFERENCES "subreceipt" ("id");

CREATE TABLE "pieceofdebt" (
  "id" SERIAL PRIMARY KEY,
  "member_ref" INTEGER NOT NULL,
  "debt_ref" INTEGER NOT NULL,
  "amount" DECIMAL(12, 2) NOT NULL,
  "paid_amount" DECIMAL(12, 2) NOT NULL
);

CREATE INDEX "idx_pieceofdebt__debt_ref" ON "pieceofdebt" ("debt_ref");

CREATE INDEX "idx_pieceofdebt__member_ref" ON "pieceofdebt" ("member_ref");

ALTER TABLE "pieceofdebt" ADD CONSTRAINT "fk_pieceofdebt__member_ref" FOREIGN KEY ("member_ref") REFERENCES "member" ("id") ON DELETE CASCADE;

CREATE TABLE "log" (
  "id" SERIAL PRIMARY KEY,
  "web_user_ref" INTEGER NOT NULL,
  "time" TIMESTAMP NOT NULL,
  "type" INTEGER NOT NULL,
  "special_type" TEXT NOT NULL,
  "detail" TEXT NOT NULL,
  "logged_bank_account_ref" INTEGER,
  "logged_retracted_ref" INTEGER,
  "logged_contribution_ref" INTEGER,
  "logged_installment_ref" INTEGER,
  "logged_debt_ref" INTEGER,
  "logged_sub_receipt_ref" INTEGER,
  "logged_piece_of_debt_ref" INTEGER,
  "logged_bank_transaction_ref" INTEGER,
  "logged_money_transaction_ref" INTEGER,
  "logged_share_ref" INTEGER,
  "logged_member_ref" INTEGER,
  "logged_sandik_ref" INTEGER,
  "logged_sms_package_ref" INTEGER,
  "logged_web_user_ref" INTEGER,
  "logged_sandik_authority_type_ref" INTEGER,
  "logged_trust_relationship_ref" INTEGER
);

CREATE INDEX "idx_log__logged_bank_account_ref" ON "log" ("logged_bank_account_ref");

CREATE INDEX "idx_log__logged_bank_transaction_ref" ON "log" ("logged_bank_transaction_ref");

CREATE INDEX "idx_log__logged_contribution_ref" ON "log" ("logged_contribution_ref");

CREATE INDEX "idx_log__logged_debt_ref" ON "log" ("logged_debt_ref");

CREATE INDEX "idx_log__logged_installment_ref" ON "log" ("logged_installment_ref");

CREATE INDEX "idx_log__logged_member_ref" ON "log" ("logged_member_ref");

CREATE INDEX "idx_log__logged_money_transaction_ref" ON "log" ("logged_money_transaction_ref");

CREATE INDEX "idx_log__logged_piece_of_debt_ref" ON "log" ("logged_piece_of_debt_ref");

CREATE INDEX "idx_log__logged_retracted_ref" ON "log" ("logged_retracted_ref");

CREATE INDEX "idx_log__logged_sandik_authority_type_ref" ON "log" ("logged_sandik_authority_type_ref");

CREATE INDEX "idx_log__logged_sandik_ref" ON "log" ("logged_sandik_ref");

CREATE INDEX "idx_log__logged_share_ref" ON "log" ("logged_share_ref");

CREATE INDEX "idx_log__logged_sms_package_ref" ON "log" ("logged_sms_package_ref");

CREATE INDEX "idx_log__logged_sub_receipt_ref" ON "log" ("logged_sub_receipt_ref");

CREATE INDEX "idx_log__logged_trust_relationship_ref" ON "log" ("logged_trust_relationship_ref");

CREATE INDEX "idx_log__logged_web_user_ref" ON "log" ("logged_web_user_ref");

CREATE INDEX "idx_log__web_user_ref" ON "log" ("web_user_ref");

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_bank_account_ref" FOREIGN KEY ("logged_bank_account_ref") REFERENCES "bankaccount" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_bank_transaction_ref" FOREIGN KEY ("logged_bank_transaction_ref") REFERENCES "banktransaction" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_contribution_ref" FOREIGN KEY ("logged_contribution_ref") REFERENCES "contribution" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_member_ref" FOREIGN KEY ("logged_member_ref") REFERENCES "member" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_money_transaction_ref" FOREIGN KEY ("logged_money_transaction_ref") REFERENCES "moneytransaction" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_piece_of_debt_ref" FOREIGN KEY ("logged_piece_of_debt_ref") REFERENCES "pieceofdebt" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_retracted_ref" FOREIGN KEY ("logged_retracted_ref") REFERENCES "retracted" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_sandik_authority_type_ref" FOREIGN KEY ("logged_sandik_authority_type_ref") REFERENCES "sandikauthoritytype" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_sandik_ref" FOREIGN KEY ("logged_sandik_ref") REFERENCES "sandik" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_share_ref" FOREIGN KEY ("logged_share_ref") REFERENCES "share" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_sms_package_ref" FOREIGN KEY ("logged_sms_package_ref") REFERENCES "smspackage" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_sub_receipt_ref" FOREIGN KEY ("logged_sub_receipt_ref") REFERENCES "subreceipt" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_trust_relationship_ref" FOREIGN KEY ("logged_trust_relationship_ref") REFERENCES "trustrelationship" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_web_user_ref" FOREIGN KEY ("logged_web_user_ref") REFERENCES "webuser" ("id") ON DELETE SET NULL;

ALTER TABLE "log" ADD CONSTRAINT "fk_log__web_user_ref" FOREIGN KEY ("web_user_ref") REFERENCES "webuser" ("id") ON DELETE CASCADE;

CREATE TABLE "installment" (
  "id" SERIAL PRIMARY KEY,
  "amount" DECIMAL(12, 2) NOT NULL,
  "term" TEXT NOT NULL,
  "is_fully_paid" BOOLEAN NOT NULL,
  "debt_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_installment__debt_ref" ON "installment" ("debt_ref");

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_installment_ref" FOREIGN KEY ("logged_installment_ref") REFERENCES "installment" ("id") ON DELETE SET NULL;

ALTER TABLE "subreceipt" ADD CONSTRAINT "fk_subreceipt__installment_ref" FOREIGN KEY ("installment_ref") REFERENCES "installment" ("id") ON DELETE SET NULL;

CREATE TABLE "debt" (
  "id" SERIAL PRIMARY KEY,
  "amount" DECIMAL(12, 2) NOT NULL,
  "number_of_installment" INTEGER NOT NULL,
  "starting_term" TEXT NOT NULL,
  "due_term" TEXT NOT NULL,
  "sub_receipt_ref" INTEGER NOT NULL,
  "share_ref" INTEGER NOT NULL
);

CREATE INDEX "idx_debt__share_ref" ON "debt" ("share_ref");

CREATE INDEX "idx_debt__sub_receipt_ref" ON "debt" ("sub_receipt_ref");

ALTER TABLE "debt" ADD CONSTRAINT "fk_debt__share_ref" FOREIGN KEY ("share_ref") REFERENCES "share" ("id") ON DELETE CASCADE;

ALTER TABLE "debt" ADD CONSTRAINT "fk_debt__sub_receipt_ref" FOREIGN KEY ("sub_receipt_ref") REFERENCES "subreceipt" ("id");

ALTER TABLE "log" ADD CONSTRAINT "fk_log__logged_debt_ref" FOREIGN KEY ("logged_debt_ref") REFERENCES "debt" ("id") ON DELETE SET NULL;

ALTER TABLE "installment" ADD CONSTRAINT "fk_installment__debt_ref" FOREIGN KEY ("debt_ref") REFERENCES "debt" ("id") ON DELETE CASCADE;

ALTER TABLE "pieceofdebt" ADD CONSTRAINT "fk_pieceofdebt__debt_ref" FOREIGN KEY ("debt_ref") REFERENCES "debt" ("id") ON DELETE CASCADE