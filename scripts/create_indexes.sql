-- =============================================================
-- UIX 性能优化索引脚本
-- 在内网 MySQL 上执行此脚本，可显著加速 metadata 和 search 查询
-- 执行前请确认数据库名称（默认 datacenter），如不同请全局替换
-- =============================================================

USE datacenter;

-- 1. 复合索引：机台 + 生产时间（最常用查询条件，search 接口核心索引）
--    作用：WHERE equipment='SSB8001' AND wafer_product_start_time BETWEEN ? AND ?
--    预期提升：大表查询从秒级降至毫秒级
CREATE INDEX IF NOT EXISTS IDX_equipment_time
    ON lo_batch_equipment_performance (equipment, wafer_product_start_time);

-- 2. 复合索引：机台 + Chuck/Lot/Wafer（metadata 去重查询）
--    作用：WHERE equipment=? -> DISTINCT chuck_id, lot_id, wafer_id
CREATE INDEX IF NOT EXISTS IDX_equipment_chuck_lot_wafer
    ON lo_batch_equipment_performance (equipment, chuck_id, lot_id, wafer_id);

-- 3. 单列索引（如已存在会跳过）
CREATE INDEX IF NOT EXISTS IDX_equipment
    ON lo_batch_equipment_performance (equipment);

CREATE INDEX IF NOT EXISTS IDX_wafer_product_start_time
    ON lo_batch_equipment_performance (wafer_product_start_time);

CREATE INDEX IF NOT EXISTS IDX_reject_reason
    ON lo_batch_equipment_performance (reject_reason);

-- 4. reject_reason_state 表（枚举表，一般很小，无需额外索引）
-- 如果需要，可以确认主键索引存在：
-- SHOW INDEX FROM reject_reason_state;

-- 验证索引是否创建成功
SHOW INDEX FROM lo_batch_equipment_performance;
