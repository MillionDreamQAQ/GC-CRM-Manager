# CRM Support Case UI

本地 B/S 应用。FastAPI 提供 Dataverse API、Azure CLI 身份验证和 SQLite 批量任务，前端使用 Vite、Vue 3、Element Plus、SortableJS 与 pinyin-pro。

## 目录

- `app.py`：FastAPI 应用与 HTTP 接口
- `dataverse_client.py`：Azure CLI 令牌、Dataverse HTTP 客户端与日期规范化
- `dataverse_gateway.py`：客户/商机来源查询、权利聚合和案例创建
- `batch_jobs.py`：SQLite 批量任务与后台执行
- `launcher.py`：Windows 本地启动器
- `frontend/`：Vue 前端源码
- `static/`：Vite 生产构建，由 FastAPI 提供
- `data/`：运行时生成，不进入发布包

## 后端启动

在项目根目录（包含 `crm_support_ui` 文件夹的目录）执行：

```powershell
python -m pip install -r requirements.txt
$env:CRM_AZ_PATH='C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
python -m uvicorn crm_support_ui.app:app --host 127.0.0.1 --port 8765
```

也可以直接运行 `start_crm_ui.cmd`。

## 前端开发

```powershell
cd crm_support_ui\frontend
npm.cmd ci
npm.cmd run dev
```

Vite 默认运行在 `http://127.0.0.1:5173`，并将 `/api` 代理到 `http://127.0.0.1:8765`。

## 构建

```powershell
cd crm_support_ui\frontend
npm.cmd ci
npm.cmd run build
```

构建结果写入 `crm_support_ui/static`。

前端测试：

```powershell
cd crm_support_ui\frontend
npm.cmd test
```

## 测试

```powershell
python -m unittest tests.test_crm_support_ui
```

工作区开发布局下使用：

```powershell
python -m unittest work.test_crm_support_ui
```

## 配置

- `CRM_ENVIRONMENT`：Dataverse 环境 URL
- `CRM_TENANT_ID`：Microsoft Entra 租户 ID
- `CRM_AZ_PATH`：Azure CLI 的完整路径
- `CRM_BATCH_DATABASE`：批量任务 SQLite 文件路径

未配置时使用当前葡萄城 CRM 环境、租户和项目内 `data/batch_jobs.db`。

## 发布包规则

发布包包含 Python 源码、前端源码、生产静态文件、依赖锁文件、测试和文档，不包含：

- `node_modules`
- `__pycache__` / `.pyc`
- SQLite 运行数据
- 日志
- Azure CLI 登录数据或令牌
