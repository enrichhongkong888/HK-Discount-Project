CREATE TYPE "DiscountCategory" AS ENUM ('商場優惠', '機票', '自助餐', '主題樂園');
CREATE TYPE "DiscountSource" AS ENUM ('SCRAPING', 'API', 'USER_SUBMIT');
CREATE TYPE "AuditStatus" AS ENUM ('PENDING', 'APPROVED', 'REJECTED');

CREATE TABLE "malls" (
    "id" SERIAL NOT NULL,
    "mall_name" VARCHAR(120) NOT NULL,
    "district" VARCHAR(50) NOT NULL,
    "address" TEXT NOT NULL,
    "phone" VARCHAR(50),
    "network_phone" VARCHAR(50),
    "mall_url" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "malls_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "brands" (
    "id" SERIAL NOT NULL,
    "name" VARCHAR(120) NOT NULL,
    "logo_url" TEXT,
    "website" TEXT,
    "description" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "brands_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "discounts" (
    "id" SERIAL NOT NULL,
    "brand_id" INTEGER,
    "mall_id" INTEGER,
    "category" "DiscountCategory" NOT NULL,
    "district" VARCHAR(50),
    "title" VARCHAR(255) NOT NULL,
    "short_desc" TEXT,
    "detail_url" TEXT NOT NULL,
    "image_url" TEXT,
    "discount_code" VARCHAR(50),
    "amount_off" DECIMAL(10,2),
    "percent_off" DECIMAL(5,2),
    "min_spend" DECIMAL(10,2),
    "gift_desc" TEXT,
    "is_daily_special" BOOLEAN NOT NULL DEFAULT false,
    "created_date" DATE NOT NULL DEFAULT CURRENT_DATE,
    "expiry_date" DATE NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "source" "DiscountSource" NOT NULL DEFAULT 'SCRAPING',
    "source_name" VARCHAR(120),
    "audit_status" "AuditStatus" NOT NULL DEFAULT 'PENDING',
    "created_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "discounts_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "malls_mall_name_district_key" ON "malls"("mall_name", "district");
CREATE UNIQUE INDEX "brands_name_key" ON "brands"("name");
CREATE UNIQUE INDEX "discounts_detail_url_key" ON "discounts"("detail_url");
CREATE INDEX "discounts_category_district_idx" ON "discounts"("category", "district");
CREATE INDEX "discounts_is_daily_special_created_at_idx" ON "discounts"("is_daily_special", "created_at");
CREATE INDEX "discounts_expiry_date_idx" ON "discounts"("expiry_date");

ALTER TABLE "discounts" ADD CONSTRAINT "discounts_brand_id_fkey"
    FOREIGN KEY ("brand_id") REFERENCES "brands"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "discounts" ADD CONSTRAINT "discounts_mall_id_fkey"
    FOREIGN KEY ("mall_id") REFERENCES "malls"("id") ON DELETE SET NULL ON UPDATE CASCADE;

CREATE OR REPLACE FUNCTION purge_expired_discounts(reference_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)
RETURNS TABLE(daily_specials_deleted BIGINT, expired_offers_deleted BIGINT)
LANGUAGE plpgsql
AS $$
DECLARE
    daily_count BIGINT;
    expiry_count BIGINT;
BEGIN
    DELETE FROM "discounts"
    WHERE "is_daily_special" = true
      AND "created_at" < reference_time - INTERVAL '1 day';
    GET DIAGNOSTICS daily_count = ROW_COUNT;

    DELETE FROM "discounts"
    WHERE "is_daily_special" = false
      AND "expiry_date" < reference_time::date;
    GET DIAGNOSTICS expiry_count = ROW_COUNT;

    RETURN QUERY SELECT daily_count, expiry_count;
END;
$$;
