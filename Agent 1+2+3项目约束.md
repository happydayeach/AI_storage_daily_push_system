项目：agent_123 新闻处理Agent链路
1. 遵循模块化：每个Agent独立类/函数
2. 配置驱动：theme_config 为唯一输入
3. 无状态：story库由外部传入，Agent内部不持久化存储
4. 保留抽象接口，同时保留模拟数据源和真实API接入点
5. 新增代码必须打印关键日志做可观测
6. 禁止擅自修改models.py的数据模型，改动前先输出diff给我确认
7. 测试运行命令: python main.py
