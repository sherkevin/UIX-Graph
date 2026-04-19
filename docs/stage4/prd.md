<!--
 * @Author: shervin sherkevin@163.com
 * @Date: 2026-04-14 09:53:48
 * @LastEditors: shervin sherkevin@163.com
 * @LastEditTime: 2026-04-15 10:07:57
 * @FilePath: \UIX-Graph\docs\stage4\prd.md
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
 * 
-->
# 建模函数参数获取
> 建模函数参数一共有四组，每组两个，相当于是四个坐标，确定了一个长方形的四个点，下面是建模参数的四个坐标的查询步骤
## 前置工作
- "WS_pos_x" （WS大写）字段所在表修改为clickhouse里的 src.RPT_WAA_V2_SET_OFL
- "WS_pos_y" （WS大写）字段所在表修改为clickhouse里的 src.RPT_WAA_V2_SET_OFL
- "mark_pos_x" 字段所在表为las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW
- "mark_pos_y" 字段所在表名为las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW

## 具体步骤
1. 找到performance主表中的一条记录，拿到对应的file_time, equipment, lot_id, wafer_index, chuck_id，这时候这些值都是确定的，可以分别表示为f，e，l，w，c
2. 在las.RPT_WAA_RESULT_OFL 表中查询mark_id，查询条件是lot_id=l && wafer_id=w && && chuck_id=c && phase ='1ST_COWA'，同时可以得到四条记录，每条记录对应一个mark_id值，一共有四个mark值，简称为m1~m4，这次搜出来可能有不止四条记录，按照row_id asc排序取前四条
3. 在las.RTP_WAA_LOT_MARK_INFO_UNION_VIEW 中查询对应的四个坐标的值，也就是说有四条记录，每条记录有一组值：mark_pox_x和mark_pox_y，查询条件是lot_id=l,mark_id = m1 or m2 or m3 or m4

## 其他相关参数的搜寻步骤
### Msx和Msy和e_ws_x和e_ws_y
1. 筛选条件为：lot_id=l && wafer_id = w chuck_id= c

### Sx和Sy
1. 查找env_id列包含（不是直接等于）e的行；
2. 找data列；
3. 按照下面data列里内容模版正则抽取对应的x和y，模板是："static_wafer_load_offset":{"chuck_message[0]":{"":"","static_load_offset":{"x":"","y":""}}}，其中这里的chuck_message[0]是chuck_id=1的情况，chuck_message[1]是chuck_id=2的情况，"static_load_offset":{"x":"","y":""} 这里的x 和 y 分别是 Sx，Sy

### D_x和D_y
- 需新增该字段
- D_x和D_y的相关信息为：
  - description：动态上片偏差x
  - db_type:"mysql"，
  - "table_name":"LO_wafer_result"，
  - "column_name"："wafer_load_offset_x"和"wafer_load_offset_y"。
  
- 筛选条件：lot_id=l && wafer_id=w && chuck_id=c
