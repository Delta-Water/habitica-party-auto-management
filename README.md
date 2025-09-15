<div align="center">

[English](/README/README_en.md)

</div>

# Habitica 小队管理工具

本项目提供自动化管理 Habitica 小队的解决方案，支持成员活跃度检测、自动邀请新成员、自动移除长期未活跃成员及每日自动更新小队简介等功能。通过 Python 脚本与 Habitica API 交互，有效提升小队管理效率。

## 主要功能

- **自动更新小队简介**：每日获取“金山每日一句”，并结合成员活跃状态信息，自动更新小队介绍内容。
- **成员活跃度检测**：定期检查小队成员最近登录时间，自动识别长期未活跃的成员。
- **自动移除未活跃成员**：对超过设定时限未登录的成员，自动发送私信通知并将其移出小队。
- **自动邀请新成员**：自动搜索正在寻找小队的用户并发送组队邀请。
- **更多功能持续更新中**
- **完整日志记录**：所有操作均记录详细日志，方便跟踪与问题排查。

## 快速开始

1. **克隆项目**
   
2. **安装依赖**  
   建议使用 Python 3.8 及以上版本。  
   执行以下命令安装依赖：  
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**  
   在 `./scripts` 目录下的 `.env` 文件中配置您的 Habitica 用户 ID 和 API Key：  
   ```
   HABITICA_USER_ID=你的用户ID
   HABITICA_API_KEY=你的API密钥
   ```

4. **运行脚本**  
   - 推荐方式（定时执行）：  
     使用 Windows 任务计划程序设置定时任务，定期执行 `./scripts/start.py`。
   
   - 手动执行（可选）：  
     - 管理成员（移除不活跃成员并邀请新成员）：  
       ```bash
       python scripts/manage_members.py
       ```
     - 更新小队简介：  
       ```bash
       python scripts/update_description.py
       ```

5. **自定义消息模板**  
   可根据需要修改 `./scripts/documents/` 目录中的队伍介绍模板和移除成员时发送的消息内容。

## 日志与调试

所有运行日志均保存在 `logs` 目录下，便于随时查看和排查问题。

## 参与贡献

欢迎通过提交 Issue 或 Pull Request 为本项目提供改进建议。贡献内容需遵循项目现有许可证协议。

## 联系方式

如有疑问或建议，请通过 GitHub Issue 与我们联系。