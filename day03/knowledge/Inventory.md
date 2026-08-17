# Unity背包系统


## InventoryManager

InventoryManager负责玩家背包管理。


主要功能：

- 添加物品
- 删除物品
- 查询物品
- 保存背包


## ItemDefinition

ItemDefinition定义物品数据。


包含：

- ID
- 名称
- 图标
- 类型
- 最大堆叠数量


## InventorySlot

InventorySlot表示背包格子。


包含：

- Item
- Count

## 数据保存

InventoryManager通常不会直接保存MonoBehaviour状态。

推荐使用：

- JSON
- SQLite
- ScriptableObject

进行数据持久化。


## 网络同步

多人游戏中：

Inventory数据需要同步服务器。

常用方案：

- Mirror
- Netcode
- RPC同步


## 性能优化

大量物品情况下：

避免每帧遍历List。

推荐：

Dictionary<ItemID,InventoryItem>