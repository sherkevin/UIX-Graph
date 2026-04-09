-- ============================================================
-- Docker MySQL 初始化脚本
-- ============================================================

USE datacenter;

-- 1. 创建 reject_reason_state 表
CREATE TABLE IF NOT EXISTS `reject_reason_state` (
  `reject_reason_id` BIGINT PRIMARY KEY COMMENT '拒片原因 ID',
  `reject_reason_value` VARCHAR(50) NOT NULL COMMENT '拒片原因值'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='拒片原因枚举值定义表';

-- 2. 创建 lo_batch_equipment_performance 表
-- 尽量对齐 docs/intranet/schema_reference.md 中已明确给出的内网字段；
-- 文档中标注“序号 58–96 待补”的未知列暂无法无中生有补齐。
CREATE TABLE IF NOT EXISTS `lo_batch_equipment_performance` (
  `id` INT AUTO_INCREMENT PRIMARY KEY COMMENT '故障记录 ID',
  `equipment` VARCHAR(50) NOT NULL COMMENT '机台名称',
  `lot_start_time` DATETIME(6) DEFAULT NULL COMMENT 'Lot 开始时间',
  `lot_end_time` DATETIME(6) DEFAULT NULL COMMENT 'Lot 结束时间',
  `seq_id_lo_wafer_mamsd_result` INT DEFAULT NULL COMMENT '内网原表字段',
  `recipe_id` VARCHAR(500) DEFAULT NULL COMMENT '工艺配方 ID',
  `layer_id` VARCHAR(500) DEFAULT NULL COMMENT '层 ID',
  `lot_id` INT NOT NULL COMMENT 'Lot ID',
  `lot_name` VARCHAR(500) DEFAULT NULL COMMENT 'Lot 名称',
  `substrate_lot_id` VARCHAR(500) DEFAULT NULL COMMENT 'Substrate lot ID',
  `wafer_index` INT NOT NULL COMMENT 'Wafer 序号 (1-25)，对应 ORM wafer_index',
  `wafer_id` VARCHAR(500) DEFAULT NULL COMMENT 'Wafer ID',
  `chuck_id` INT NOT NULL COMMENT 'Chuck ID',
  `wafer_translation_x` DECIMAL(18,9) DEFAULT NULL COMMENT 'COWA 建模输出 Tx',
  `wafer_translation_y` DECIMAL(18,9) DEFAULT NULL COMMENT 'COWA 建模输出 Ty',
  `wafer_expansion_x` DECIMAL(18,9) DEFAULT NULL COMMENT 'Wafer expansion x',
  `wafer_expansion_y` DECIMAL(18,9) DEFAULT NULL COMMENT 'Wafer expansion y',
  `wafer_rotation` DECIMAL(18,3) DEFAULT NULL COMMENT 'COWA 建模输出 Rw',
  `wafer_non_orthogonal` DECIMAL(18,3) DEFAULT NULL COMMENT 'Wafer non orthogonal',
  `std_wafer_translation_x` DECIMAL(18,9) DEFAULT NULL COMMENT 'Std wafer translation x',
  `std_wafer_translation_y` DECIMAL(18,9) DEFAULT NULL COMMENT 'Std wafer translation y',
  `std_wafer_rotation` DECIMAL(18,3) DEFAULT NULL COMMENT 'Std wafer rotation',
  `max_ws_x_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_x_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_y_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_y_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_rz_ma` DECIMAL(18,9) DEFAULT NULL,
  `max_ws_rz_msd` DECIMAL(18,9) DEFAULT NULL,
  `max_ws_z_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_z_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_x_total_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_x_total_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_y_total_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_y_total_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_z_total_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_ws_z_total_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_x_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_x_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_y_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_y_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_rz_ma` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_rz_msd` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_diff_x_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_diff_x_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_diff_y_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_diff_y_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_diff_rz_ma` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_diff_rz_msd` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_z_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_z_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_rx_ma` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_rx_msd` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_ry_ma` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_ry_msd` DECIMAL(18,9) DEFAULT NULL,
  `max_rs_x_total_ma` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_x_total_msd` DECIMAL(18,6) DEFAULT NULL,
  `max_rs_y_total_ma` DECIMAL(18,6) DEFAULT NULL,
  `lot_end_lens_temp` DECIMAL(18,6) DEFAULT NULL,
  `lot_end_lens_pressure` DECIMAL(18,6) DEFAULT NULL,
  `lot_start_lens_temp` DECIMAL(18,6) DEFAULT NULL,
  `lot_start_lens_pressure` DECIMAL(18,6) DEFAULT NULL,
  `dose_err_ilpe_min` DECIMAL(18,9) DEFAULT NULL,
  `dose_err_ilpe_max` DECIMAL(18,9) DEFAULT NULL,
  `dose_err_ilpe_mean` DECIMAL(18,9) DEFAULT NULL,
  `dose_err_elpe_max` DECIMAL(18,9) DEFAULT NULL,
  `dose_err_elpe_min` DECIMAL(18,9) DEFAULT NULL,
  `dose_err_elpe_mean` DECIMAL(18,9) DEFAULT NULL,
  `actual_energy` DECIMAL(18,9) DEFAULT NULL,
  `focus_z` DECIMAL(18,9) DEFAULT NULL,
  `image_size_x` DECIMAL(18,9) DEFAULT NULL,
  `image_size_y` DECIMAL(18,9) DEFAULT NULL,
  `creation_date` DATETIME DEFAULT NULL,
  `wafer_product_start_time` DATETIME(6) NOT NULL COMMENT 'Wafer 生产开始时间',
  `wafer_state` BIGINT DEFAULT NULL,
  `reject_reason` BIGINT NOT NULL COMMENT '拒片原因 ID（外键）',
  `insert_time` DATETIME DEFAULT NULL,
  INDEX `IDX_equipment` (`equipment`),
  INDEX `IDX_chuck_lot_wafer` (`chuck_id`, `lot_id`, `wafer_index`),
  INDEX `IDX_wafer_product_start_time` (`wafer_product_start_time`),
  INDEX `IDX_lot_start_end_time` (`lot_start_time`, `lot_end_time`),
  INDEX `IDX_reject_reason` (`reject_reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='机台生产过程中的批次、性能、拒片等原始数据表';

-- 3. 创建 rejected_detailed_records 缓存表
CREATE TABLE IF NOT EXISTS `rejected_detailed_records` (
  `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
  `failure_id` BIGINT NOT NULL COMMENT '故障记录 ID（关联源表 ID）',
  `equipment` VARCHAR(50) NOT NULL COMMENT '机台名称',
  `chuck_id` INT NOT NULL COMMENT 'Chuck ID',
  `lot_id` INT NOT NULL COMMENT 'Lot ID',
  `wafer_id` INT NOT NULL COMMENT 'Wafer ID',
  `occurred_at` DATETIME(6) NOT NULL COMMENT '故障发生时间',
  `reject_reason` VARCHAR(50) NOT NULL COMMENT '拒片原因值',
  `reject_reason_id` BIGINT NOT NULL COMMENT '拒片原因 ID',
  `root_cause` VARCHAR(255) DEFAULT NULL COMMENT '根本原因',
  `system` VARCHAR(50) DEFAULT NULL COMMENT '所属分系统',
  `error_field` VARCHAR(255) DEFAULT NULL COMMENT '报错字段',
  `metrics_data` JSON DEFAULT NULL COMMENT '指标数据（含 status）',
  `created_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
  `updated_at` DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
  UNIQUE KEY `UK_failure_id` (`failure_id`),
  INDEX `IDX_equipment` (`equipment`),
  INDEX `IDX_occurred_at` (`occurred_at`),
  INDEX `IDX_chuck_lot_wafer` (`chuck_id`, `lot_id`, `wafer_id`),
  INDEX `IDX_reject_reason` (`reject_reason`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='拒片详细记录表';

-- ============================================================
-- 插入 reject_reason_state 枚举数据
-- ============================================================
INSERT IGNORE INTO `reject_reason_state` (`reject_reason_id`, `reject_reason_value`) VALUES
(6,    'COARSE_ALIGN_FAILED'),
(5001, 'MEASURE_FAILED'),
(5002, 'ALIGNMENT_FAILED'),
(5003, 'OVERLAY_EXCEEDED'),
(5004, 'FOCUS_FAILED'),
(5005, 'WAFER_ROTATION_EXCEEDED'),
(5006, 'MAGNIFICATION_EXCEEDED'),
(5007, 'RESIDUAL_EXCEEDED'),
(5008, 'VACUUM_FAILED'),
(5009, 'MARK_RECOGNITION_FAILED'),
(5010, 'SCAN_ERROR');

-- ============================================================
-- 插入 lo_batch_equipment_performance Mock 数据
-- 覆盖多台机台、多个 Chuck/Lot/Wafer 组合
-- ============================================================

-- SSB8000 机台数据
INSERT INTO `lo_batch_equipment_performance`
  (`equipment`, `chuck_id`, `lot_id`, `wafer_index`, `lot_start_time`, `lot_end_time`, `wafer_product_start_time`, `reject_reason`)
VALUES
-- Chuck 1, Lot 101
('SSB8000', 1, 101, 1,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 08:05:00.000000', 5001),
('SSB8000', 1, 101, 3,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 08:20:00.000000', 5002),
('SSB8000', 1, 101, 5,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 08:35:00.000000', 5001),
('SSB8000', 1, 101, 7,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 08:50:00.000000', 5003),
('SSB8000', 1, 101, 12, '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 09:10:00.000000', 5002),
-- Chuck 1, Lot 102
('SSB8000', 1, 102, 2,  '2026-01-11 09:00:00.000000', '2026-01-11 11:00:00.000000', '2026-01-11 09:10:00.000000', 5004),
('SSB8000', 1, 102, 4,  '2026-01-11 09:00:00.000000', '2026-01-11 11:00:00.000000', '2026-01-11 09:25:00.000000', 5005),
('SSB8000', 1, 102, 8,  '2026-01-11 09:00:00.000000', '2026-01-11 11:00:00.000000', '2026-01-11 09:40:00.000000', 5001),
('SSB8000', 1, 102, 15, '2026-01-11 09:00:00.000000', '2026-01-11 11:00:00.000000', '2026-01-11 09:55:00.000000', 5003),
-- Chuck 2, Lot 201
('SSB8000', 2, 201, 1,  '2026-01-12 10:00:00.000000', '2026-01-12 12:00:00.000000', '2026-01-12 10:05:00.000000', 5006),
('SSB8000', 2, 201, 6,  '2026-01-12 10:00:00.000000', '2026-01-12 12:00:00.000000', '2026-01-12 10:20:00.000000', 5007),
('SSB8000', 2, 201, 11, '2026-01-12 10:00:00.000000', '2026-01-12 12:00:00.000000', '2026-01-12 10:35:00.000000', 5002),
('SSB8000', 2, 201, 18, '2026-01-12 10:00:00.000000', '2026-01-12 12:00:00.000000', '2026-01-12 10:50:00.000000', 5008),
-- Chuck 2, Lot 202
('SSB8000', 2, 202, 3,  '2026-01-13 08:30:00.000000', '2026-01-13 10:30:00.000000', '2026-01-13 08:35:00.000000', 5009),
('SSB8000', 2, 202, 9,  '2026-01-13 08:30:00.000000', '2026-01-13 10:30:00.000000', '2026-01-13 08:50:00.000000', 5010),
('SSB8000', 2, 202, 14, '2026-01-13 08:30:00.000000', '2026-01-13 10:30:00.000000', '2026-01-13 09:05:00.000000', 5001),
('SSB8000', 2, 202, 20, '2026-01-13 08:30:00.000000', '2026-01-13 10:30:00.000000', '2026-01-13 09:20:00.000000', 5002),
-- Chuck 3, Lot 301
('SSB8000', 3, 301, 2,  '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 11:05:00.000000', 5003),
('SSB8000', 3, 301, 5,  '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 11:20:00.000000', 5004),
('SSB8000', 3, 301, 10, '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 11:35:00.000000', 5005),
('SSB8000', 3, 301, 16, '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 11:50:00.000000', 5006),
('SSB8000', 3, 301, 22, '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 12:05:00.000000', 5007),

-- SSB8001 机台数据
('SSB8001', 1, 101, 2,  '2026-01-15 08:00:00.000000', '2026-01-15 10:00:00.000000', '2026-01-15 08:10:00.000000', 5001),
('SSB8001', 1, 101, 8,  '2026-01-15 08:00:00.000000', '2026-01-15 10:00:00.000000', '2026-01-15 08:25:00.000000', 5002),
('SSB8001', 1, 101, 13, '2026-01-15 08:00:00.000000', '2026-01-15 10:00:00.000000', '2026-01-15 08:40:00.000000', 5003),
('SSB8001', 2, 201, 4,  '2026-01-16 09:00:00.000000', '2026-01-16 11:00:00.000000', '2026-01-16 09:15:00.000000', 5004),
('SSB8001', 2, 201, 9,  '2026-01-16 09:00:00.000000', '2026-01-16 11:00:00.000000', '2026-01-16 09:30:00.000000', 5005),
('SSB8001', 2, 201, 17, '2026-01-16 09:00:00.000000', '2026-01-16 11:00:00.000000', '2026-01-16 09:45:00.000000', 5001),
('SSB8001', 3, 301, 1,  '2026-01-17 10:00:00.000000', '2026-01-17 12:00:00.000000', '2026-01-17 10:05:00.000000', 5006),
('SSB8001', 3, 301, 7,  '2026-01-17 10:00:00.000000', '2026-01-17 12:00:00.000000', '2026-01-17 10:20:00.000000', 5007),

-- SSC8001 机台数据
('SSC8001', 1, 101, 3,  '2026-01-18 08:00:00.000000', '2026-01-18 10:00:00.000000', '2026-01-18 08:05:00.000000', 5008),
('SSC8001', 1, 101, 6,  '2026-01-18 08:00:00.000000', '2026-01-18 10:00:00.000000', '2026-01-18 08:20:00.000000', 5009),
('SSC8001', 1, 101, 11, '2026-01-18 08:00:00.000000', '2026-01-18 10:00:00.000000', '2026-01-18 08:35:00.000000', 5010),
('SSC8001', 1, 102, 2,  '2026-01-19 09:00:00.000000', '2026-01-19 11:00:00.000000', '2026-01-19 09:10:00.000000', 5001),
('SSC8001', 1, 102, 7,  '2026-01-19 09:00:00.000000', '2026-01-19 11:00:00.000000', '2026-01-19 09:25:00.000000', 5002),
('SSC8001', 2, 201, 5,  '2026-01-20 10:00:00.000000', '2026-01-20 12:00:00.000000', '2026-01-20 10:10:00.000000', 5003),
('SSC8001', 2, 201, 10, '2026-01-20 10:00:00.000000', '2026-01-20 12:00:00.000000', '2026-01-20 10:25:00.000000', 5004),
('SSC8001', 2, 201, 19, '2026-01-20 10:00:00.000000', '2026-01-20 12:00:00.000000', '2026-01-20 10:40:00.000000', 5005),

-- SSC8002 机台数据
('SSC8002', 1, 101, 1,  '2026-02-01 08:00:00.000000', '2026-02-01 10:00:00.000000', '2026-02-01 08:05:00.000000', 5001),
('SSC8002', 1, 101, 4,  '2026-02-01 08:00:00.000000', '2026-02-01 10:00:00.000000', '2026-02-01 08:20:00.000000', 5006),
('SSC8002', 1, 101, 9,  '2026-02-01 08:00:00.000000', '2026-02-01 10:00:00.000000', '2026-02-01 08:35:00.000000', 5007),
('SSC8002', 2, 201, 2,  '2026-02-02 09:00:00.000000', '2026-02-02 11:00:00.000000', '2026-02-02 09:10:00.000000', 5002),
('SSC8002', 2, 201, 8,  '2026-02-02 09:00:00.000000', '2026-02-02 11:00:00.000000', '2026-02-02 09:25:00.000000', 5003),
('SSC8002', 2, 201, 13, '2026-02-02 09:00:00.000000', '2026-02-02 11:00:00.000000', '2026-02-02 09:40:00.000000', 5008),

-- SSB8005 机台数据（最近时间段）
('SSB8005', 1, 101, 1,  '2026-03-01 08:00:00.000000', '2026-03-01 10:00:00.000000', '2026-03-01 08:05:00.000000', 5001),
('SSB8005', 1, 101, 5,  '2026-03-01 08:00:00.000000', '2026-03-01 10:00:00.000000', '2026-03-01 08:20:00.000000', 5002),
('SSB8005', 1, 101, 10, '2026-03-01 08:00:00.000000', '2026-03-01 10:00:00.000000', '2026-03-01 08:35:00.000000', 5003),
('SSB8005', 1, 101, 15, '2026-03-01 08:00:00.000000', '2026-03-01 10:00:00.000000', '2026-03-01 08:50:00.000000', 5004),
('SSB8005', 1, 101, 20, '2026-03-01 08:00:00.000000', '2026-03-01 10:00:00.000000', '2026-03-01 09:05:00.000000', 5005),
('SSB8005', 2, 201, 3,  '2026-03-02 09:00:00.000000', '2026-03-02 11:00:00.000000', '2026-03-02 09:10:00.000000', 5006),
('SSB8005', 2, 201, 7,  '2026-03-02 09:00:00.000000', '2026-03-02 11:00:00.000000', '2026-03-02 09:25:00.000000', 5007),
('SSB8005', 2, 201, 12, '2026-03-02 09:00:00.000000', '2026-03-02 11:00:00.000000', '2026-03-02 09:40:00.000000', 5008),
('SSB8005', 2, 201, 18, '2026-03-02 09:00:00.000000', '2026-03-02 11:00:00.000000', '2026-03-02 09:55:00.000000', 5009),
('SSB8005', 3, 301, 2,  '2026-03-05 10:00:00.000000', '2026-03-05 12:00:00.000000', '2026-03-05 10:05:00.000000', 5010),
('SSB8005', 3, 301, 6,  '2026-03-05 10:00:00.000000', '2026-03-05 12:00:00.000000', '2026-03-05 10:20:00.000000', 5001),
('SSB8005', 3, 301, 11, '2026-03-05 10:00:00.000000', '2026-03-05 12:00:00.000000', '2026-03-05 10:35:00.000000', 5002),
('SSB8005', 3, 301, 16, '2026-03-05 10:00:00.000000', '2026-03-05 12:00:00.000000', '2026-03-05 10:50:00.000000', 5003),
('SSB8005', 3, 301, 21, '2026-03-05 10:00:00.000000', '2026-03-05 12:00:00.000000', '2026-03-05 11:05:00.000000', 5004);

-- ============================================================
-- 插入 COARSE_ALIGN_FAILED (reject_reason=6) 样例数据
-- 包含 wafer_translation_x/y/rotation 指标值，用于诊断引擎测试
-- ============================================================

-- SSB8000: Chuck 1, Lot 101 - Tx 超限(25.5 > 20) → 上片工艺适应性问题/COWA分系统
INSERT INTO `lo_batch_equipment_performance`
  (`equipment`, `chuck_id`, `lot_id`, `wafer_index`, `lot_start_time`, `lot_end_time`, `wafer_product_start_time`, `reject_reason`, `wafer_translation_x`, `wafer_translation_y`, `wafer_rotation`, `recipe_id`)
VALUES
('SSB8000', 1, 101, 7,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 08:45:00.000000', 6, 25.5,  3.2,   150.0, 'RCP-DOCKER-001'),
-- SSB8000: Chuck 1, Lot 101 - Rw 超限(450.3 > 300) → 上片工艺适应性问题/COWA分系统
('SSB8000', 1, 101, 9,  '2026-01-10 08:00:00.000000', '2026-01-10 10:00:00.000000', '2026-01-10 09:10:00.000000', 6,  5.1, -2.8,   450.3, 'RCP-DOCKER-001'),
-- SSB8000: Chuck 1, Lot 102 - 全部正常(Tx/Ty/Rw均在范围内，走normal路径)
('SSB8000', 1, 102, 2,  '2026-01-11 09:00:00.000000', '2026-01-11 11:00:00.000000', '2026-01-11 09:30:00.000000', 6,  3.5,  1.2,   100.0, 'RCP-DOCKER-001'),
-- SSB8000: Chuck 2, Lot 201 - Tx 超限(25.5 > 20) → 上片工艺适应性问题/COWA分系统
('SSB8000', 2, 201, 5,  '2026-01-12 10:00:00.000000', '2026-01-12 12:00:00.000000', '2026-01-12 10:15:00.000000', 6, 25.5,  3.2,   150.0, 'RCP-DOCKER-002'),
-- SSB8000: Chuck 2, Lot 202 - Ty 超限(-28.0 < -20) → 上片工艺适应性问题/COWA分系统
('SSB8000', 2, 202, 7,  '2026-01-13 08:30:00.000000', '2026-01-13 10:30:00.000000', '2026-01-13 08:42:00.000000', 6,  3.5,-28.0,   120.0, 'RCP-DOCKER-002'),
-- SSB8000: Chuck 3, Lot 301 - Rw 超限(350.0 > 300) → 上片工艺适应性问题/COWA分系统
('SSB8000', 3, 301, 8,  '2026-01-14 11:00:00.000000', '2026-01-14 13:00:00.000000', '2026-01-14 11:28:00.000000', 6,  5.0, -3.0,   350.0, 'RCP-DOCKER-003'),
-- SSB8001: Chuck 2, Lot 201 - Ty 超限(-28.7 < -20) → 上片工艺适应性问题/COWA分系统
('SSB8001', 2, 201, 4,  '2026-02-15 09:00:00.000000', '2026-02-15 11:00:00.000000', '2026-02-15 09:25:00.000000', 6, -1.5,-28.7,    80.0, 'RCP-DOCKER-004'),
-- SSB8001: Chuck 2, Lot 201 - Tx 超限(22.0 > 20) → 上片工艺适应性问题/COWA分系统
('SSB8001', 2, 201, 8,  '2026-02-15 09:00:00.000000', '2026-02-15 11:00:00.000000', '2026-02-15 09:50:00.000000', 6, 22.0,  1.1,   -50.0, 'RCP-DOCKER-004'),
-- SSC8001: Chuck 1, Lot 101 - Tx/Ty 均在范围内但 Rw 接近边界
('SSC8001', 1, 101, 3,  '2026-03-01 07:00:00.000000', '2026-03-01 09:00:00.000000', '2026-03-01 07:15:00.000000', 6, 18.5,-15.2,   280.0, 'RCP-DOCKER-005'),
-- SSC8001: Chuck 1, Lot 101 - Tx 和 Rw 均超限
('SSC8001', 1, 101, 11, '2026-03-01 07:00:00.000000', '2026-03-01 09:00:00.000000', '2026-03-01 07:45:00.000000', 6,-30.2, 25.8,  -400.5, 'RCP-DOCKER-005'),
-- SSC8001: Chuck 2, Lot 201 - 全部接近边界但未超限
('SSC8001', 2, 201, 5,  '2026-03-01 09:00:00.000000', '2026-03-01 11:00:00.000000', '2026-03-01 09:20:00.000000', 6, 19.9,-19.5,   299.0, 'RCP-DOCKER-006');

-- ============================================================
-- mc_config_commits_history（Sx/Sy 诊断取数；与内网 DDL 对齐）
-- last_modify_date 落在 COARSE 样例 T 的 [T-1000min, T] 窗口内
-- ============================================================
CREATE TABLE IF NOT EXISTS `mc_config_commits_history` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `table_name` VARCHAR(50) NOT NULL,
  `last_modifier` VARCHAR(50) DEFAULT NULL,
  `last_modify_date` VARCHAR(50) NOT NULL,
  `commit` VARCHAR(50) DEFAULT NULL,
  `env_id` VARCHAR(50) DEFAULT NULL,
  `data` LONGTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='MC 配置提交历史';

INSERT INTO `mc_config_commits_history` (`table_name`, `last_modifier`, `last_modify_date`, `commit`, `env_id`, `data`) VALUES
('chuck_static_offset', 'docker_seed', '2026-01-10 08:40:00', 'seed1', 'local', '{"Sx": 0.001234, "Sy": -0.005678}');

SELECT 'Tables created and data inserted successfully!' AS status;
SELECT COUNT(*) AS total_records FROM lo_batch_equipment_performance;
SELECT COUNT(*) AS total_reasons FROM reject_reason_state;
