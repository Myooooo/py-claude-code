"""成本追踪模块 - 追踪API使用成本."""

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from enum import Enum


class ModelPricing:
    """模型定价配置."""

    # 定价: 每1M tokens的价格 (USD)
    PRICES: dict[str, dict[str, float]] = {
        "gpt-4o": {
            "input": 2.50,
            "output": 10.00,
        },
        "gpt-4o-mini": {
            "input": 0.15,
            "output": 0.60,
        },
        "gpt-4-turbo": {
            "input": 10.00,
            "output": 30.00,
        },
        "gpt-3.5-turbo": {
            "input": 0.50,
            "output": 1.50,
        },
        "gpt-3.5-turbo-0125": {
            "input": 0.50,
            "output": 1.50,
        },
        "gpt-4": {
            "input": 30.00,
            "output": 60.00,
        },
        "gpt-4-32k": {
            "input": 60.00,
            "output": 120.00,
        },
    }

    @classmethod
    def get_price(cls, model: str, token_type: str) -> float:
        """获取模型价格.

        Args:
            model: 模型名称
            token_type: 'input' 或 'output'

        Returns:
            每1M tokens的价格 (USD)
        """
        # 尝试精确匹配
        if model in cls.PRICES:
            return cls.PRICES[model].get(token_type, 0.0)

        # 尝试前缀匹配 (例如 gpt-4o-2024-08-06 -> gpt-4o)
        for base_model, prices in cls.PRICES.items():
            if model.startswith(base_model):
                return prices.get(token_type, 0.0)

        # 默认使用 gpt-4o-mini 的价格 (最便宜)
        return cls.PRICES["gpt-4o-mini"].get(token_type, 0.0)

    @classmethod
    def calculate_cost(cls, model: str, input_tokens: int, output_tokens: int) -> dict[str, float]:
        """计算API调用成本.

        Args:
            model: 模型名称
            input_tokens: 输入token数
            output_tokens: 输出token数

        Returns:
            包含input_cost, output_cost, total_cost的字典
        """
        input_price = cls.get_price(model, "input")
        output_price = cls.get_price(model, "output")

        # 计算成本: tokens / 1M * price
        input_cost = (input_tokens / 1_000_000) * input_price
        output_cost = (output_tokens / 1_000_000) * output_price

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(input_cost + output_cost, 6),
            "input_price": input_price,
            "output_price": output_price,
        }


@dataclass
class CostRecord:
    """单次API调用成本记录."""

    id: Optional[int] = None
    session_id: Optional[str] = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0
    timestamp: str = ""
    request_type: str = "chat"  # chat, tool_call, summarization, etc.
    metadata: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "CostRecord":
        """从数据库行创建."""
        metadata = None
        if row["metadata"]:
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                pass

        return cls(
            id=row["id"],
            session_id=row["session_id"],
            model=row["model"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            input_cost=row["input_cost"],
            output_cost=row["output_cost"],
            total_cost=row["total_cost"],
            timestamp=row["timestamp"],
            request_type=row["request_type"],
            metadata=metadata,
        )


@dataclass
class CostSummary:
    """成本汇总."""

    period: str = ""
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_input_cost: float = 0.0
    total_output_cost: float = 0.0
    total_cost: float = 0.0
    model_breakdown: dict[str, dict[str, Any]] = None
    daily_breakdown: dict[str, dict[str, Any]] = None

    def __post_init__(self):
        if self.model_breakdown is None:
            self.model_breakdown = {}
        if self.daily_breakdown is None:
            self.daily_breakdown = {}

    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "period": self.period,
            "total_requests": self.total_requests,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_input_cost": round(self.total_input_cost, 6),
            "total_output_cost": round(self.total_output_cost, 6),
            "total_cost": round(self.total_cost, 6),
            "model_breakdown": self.model_breakdown,
            "daily_breakdown": self.daily_breakdown,
        }


@dataclass
class BudgetConfig:
    """预算配置."""

    daily_budget: float = 10.0  # USD
    weekly_budget: float = 50.0
    monthly_budget: float = 200.0
    warning_threshold: float = 0.8  # 80%时警告

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetConfig":
        return cls(
            daily_budget=data.get("daily_budget", 10.0),
            weekly_budget=data.get("weekly_budget", 50.0),
            monthly_budget=data.get("monthly_budget", 200.0),
            warning_threshold=data.get("warning_threshold", 0.8),
        )


class CostTracker:
    """成本追踪器 - SQLite实现."""

    SCHEMA_VERSION = 1

    def __init__(self, db_path: str = ".claude_costs.db"):
        """初始化成本追踪器."""
        self.db_path = Path(db_path)
        self._ensure_db_dir()
        self._init_tables()
        self._budget_config = self._load_budget_config()

    def _ensure_db_dir(self) -> None:
        """确保数据库目录存在."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self) -> None:
        """初始化数据库表."""
        with self._get_connection() as conn:
            # 成本记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cost_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    model TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    input_cost REAL DEFAULT 0.0,
                    output_cost REAL DEFAULT 0.0,
                    total_cost REAL DEFAULT 0.0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    request_type TEXT DEFAULT 'chat',
                    metadata TEXT
                )
            """)

            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_session
                ON cost_records(session_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_timestamp
                ON cost_records(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cost_model
                ON cost_records(model)
            """)

            # 预算配置表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    daily_budget REAL DEFAULT 10.0,
                    weekly_budget REAL DEFAULT 50.0,
                    monthly_budget REAL DEFAULT 200.0,
                    warning_threshold REAL DEFAULT 0.8,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 插入默认预算配置
            conn.execute("""
                INSERT OR IGNORE INTO budget_config (id, daily_budget, weekly_budget, monthly_budget, warning_threshold)
                VALUES (1, 10.0, 50.0, 200.0, 0.8)
            """)

            # 元数据表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                INSERT OR REPLACE INTO metadata (key, value, updated_at)
                VALUES ('schema_version', ?, CURRENT_TIMESTAMP)
            """, (str(self.SCHEMA_VERSION),))

            conn.commit()

    def _load_budget_config(self) -> BudgetConfig:
        """加载预算配置."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM budget_config WHERE id = 1"
                )
                row = cursor.fetchone()
                if row:
                    return BudgetConfig(
                        daily_budget=row["daily_budget"],
                        weekly_budget=row["weekly_budget"],
                        monthly_budget=row["monthly_budget"],
                        warning_threshold=row["warning_threshold"],
                    )
        except Exception as e:
            print(f"加载预算配置失败: {e}")
        return BudgetConfig()

    def record_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
        request_type: str = "chat",
        metadata: Optional[dict[str, Any]] = None,
    ) -> CostRecord:
        """记录API调用成本.

        Args:
            model: 使用的模型
            input_tokens: 输入token数
            output_tokens: 输出token数
            session_id: 会话ID
            request_type: 请求类型
            metadata: 额外元数据

        Returns:
            CostRecord对象
        """
        # 计算成本
        cost_info = ModelPricing.calculate_cost(model, input_tokens, output_tokens)

        record = CostRecord(
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=cost_info["input_cost"],
            output_cost=cost_info["output_cost"],
            total_cost=cost_info["total_cost"],
            timestamp=datetime.now().isoformat(),
            request_type=request_type,
            metadata=metadata,
        )

        try:
            with self._get_connection() as conn:
                metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None

                cursor = conn.execute("""
                    INSERT INTO cost_records
                    (session_id, model, input_tokens, output_tokens, total_tokens,
                     input_cost, output_cost, total_cost, timestamp, request_type, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.session_id,
                    record.model,
                    record.input_tokens,
                    record.output_tokens,
                    record.total_tokens,
                    record.input_cost,
                    record.output_cost,
                    record.total_cost,
                    record.timestamp,
                    record.request_type,
                    metadata_json,
                ))
                conn.commit()
                record.id = cursor.lastrowid
        except Exception as e:
            print(f"记录成本失败: {e}")

        return record

    def get_session_costs(self, session_id: str) -> CostSummary:
        """获取会话成本汇总."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(input_tokens) as total_input_tokens,
                        SUM(output_tokens) as total_output_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(input_cost) as total_input_cost,
                        SUM(output_cost) as total_output_cost,
                        SUM(total_cost) as total_cost
                    FROM cost_records
                    WHERE session_id = ?
                """, (session_id,))

                row = cursor.fetchone()
                if row:
                    return CostSummary(
                        period=f"session:{session_id}",
                        total_requests=row["total_requests"] or 0,
                        total_input_tokens=row["total_input_tokens"] or 0,
                        total_output_tokens=row["total_output_tokens"] or 0,
                        total_tokens=row["total_tokens"] or 0,
                        total_input_cost=row["total_input_cost"] or 0.0,
                        total_output_cost=row["total_output_cost"] or 0.0,
                        total_cost=row["total_cost"] or 0.0,
                    )
        except Exception as e:
            print(f"获取会话成本失败: {e}")

        return CostSummary(period=f"session:{session_id}")

    def get_daily_summary(self, date: Optional[datetime] = None) -> CostSummary:
        """获取每日成本汇总."""
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")
        start_time = f"{date_str} 00:00:00"
        end_time = f"{date_str} 23:59:59"

        return self._get_summary_for_period(start_time, end_time, f"daily:{date_str}")

    def get_weekly_summary(self, date: Optional[datetime] = None) -> CostSummary:
        """获取每周成本汇总."""
        if date is None:
            date = datetime.now()

        # 获取本周开始 (周一)
        monday = date - timedelta(days=date.weekday())
        sunday = monday + timedelta(days=6)

        start_time = monday.strftime("%Y-%m-%d 00:00:00")
        end_time = sunday.strftime("%Y-%m-%d 23:59:59")
        week_str = monday.strftime("%Y-W%W")

        return self._get_summary_for_period(start_time, end_time, f"weekly:{week_str}")

    def get_monthly_summary(self, date: Optional[datetime] = None) -> CostSummary:
        """获取每月成本汇总."""
        if date is None:
            date = datetime.now()

        year = date.year
        month = date.month

        start_time = f"{year}-{month:02d}-01 00:00:00"
        # 获取月末
        if month == 12:
            end_time = f"{year}-{month:02d}-31 23:59:59"
        else:
            next_month = datetime(year, month + 1, 1) - timedelta(days=1)
            end_time = next_month.strftime("%Y-%m-%d 23:59:59")

        month_str = f"{year}-{month:02d}"
        return self._get_summary_for_period(start_time, end_time, f"monthly:{month_str}")

    def get_all_time_summary(self) -> CostSummary:
        """获取全部时间成本汇总."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(input_tokens) as total_input_tokens,
                        SUM(output_tokens) as total_output_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(input_cost) as total_input_cost,
                        SUM(output_cost) as total_output_cost,
                        SUM(total_cost) as total_cost
                    FROM cost_records
                """)

                row = cursor.fetchone()
                summary = CostSummary(
                    period="all_time",
                    total_requests=row["total_requests"] or 0,
                    total_input_tokens=row["total_input_tokens"] or 0,
                    total_output_tokens=row["total_output_tokens"] or 0,
                    total_tokens=row["total_tokens"] or 0,
                    total_input_cost=row["total_input_cost"] or 0.0,
                    total_output_cost=row["total_output_cost"] or 0.0,
                    total_cost=row["total_cost"] or 0.0,
                )

                # 获取模型细分
                summary.model_breakdown = self._get_model_breakdown(conn)

                return summary
        except Exception as e:
            print(f"获取总成本失败: {e}")

        return CostSummary(period="all_time")

    def _get_summary_for_period(
        self, start_time: str, end_time: str, period_name: str
    ) -> CostSummary:
        """获取指定时间段的成本汇总."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT
                        COUNT(*) as total_requests,
                        SUM(input_tokens) as total_input_tokens,
                        SUM(output_tokens) as total_output_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(input_cost) as total_input_cost,
                        SUM(output_cost) as total_output_cost,
                        SUM(total_cost) as total_cost
                    FROM cost_records
                    WHERE timestamp >= ? AND timestamp <= ?
                """, (start_time, end_time))

                row = cursor.fetchone()
                summary = CostSummary(
                    period=period_name,
                    total_requests=row["total_requests"] or 0,
                    total_input_tokens=row["total_input_tokens"] or 0,
                    total_output_tokens=row["total_output_tokens"] or 0,
                    total_tokens=row["total_tokens"] or 0,
                    total_input_cost=row["total_input_cost"] or 0.0,
                    total_output_cost=row["total_output_cost"] or 0.0,
                    total_cost=row["total_cost"] or 0.0,
                )

                # 获取模型细分
                summary.model_breakdown = self._get_model_breakdown(conn, start_time, end_time)

                # 获取每日细分
                summary.daily_breakdown = self._get_daily_breakdown(conn, start_time, end_time)

                return summary
        except Exception as e:
            print(f"获取成本汇总失败: {e}")

        return CostSummary(period=period_name)

    def _get_model_breakdown(
        self, conn: sqlite3.Connection, start_time: Optional[str] = None, end_time: Optional[str] = None
    ) -> dict[str, dict[str, Any]]:
        """获取模型成本细分."""
        breakdown = {}

        try:
            if start_time and end_time:
                cursor = conn.execute("""
                    SELECT
                        model,
                        COUNT(*) as requests,
                        SUM(input_tokens) as input_tokens,
                        SUM(output_tokens) as output_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(total_cost) as cost
                    FROM cost_records
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY model
                """, (start_time, end_time))
            else:
                cursor = conn.execute("""
                    SELECT
                        model,
                        COUNT(*) as requests,
                        SUM(input_tokens) as input_tokens,
                        SUM(output_tokens) as output_tokens,
                        SUM(total_tokens) as total_tokens,
                        SUM(total_cost) as cost
                    FROM cost_records
                    GROUP BY model
                """)

            for row in cursor.fetchall():
                breakdown[row["model"]] = {
                    "requests": row["requests"],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "total_tokens": row["total_tokens"],
                    "cost": round(row["cost"], 6),
                }
        except Exception as e:
            print(f"获取模型细分失败: {e}")

        return breakdown

    def _get_daily_breakdown(
        self, conn: sqlite3.Connection, start_time: str, end_time: str
    ) -> dict[str, dict[str, Any]]:
        """获取每日成本细分."""
        breakdown = {}

        try:
            cursor = conn.execute("""
                SELECT
                    date(timestamp) as day,
                    COUNT(*) as requests,
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as cost
                FROM cost_records
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY date(timestamp)
            """, (start_time, end_time))

            for row in cursor.fetchall():
                breakdown[row["day"]] = {
                    "requests": row["requests"],
                    "total_tokens": row["total_tokens"],
                    "cost": round(row["cost"], 6),
                }
        except Exception as e:
            print(f"获取每日细分失败: {e}")

        return breakdown

    def check_budget_warnings(self) -> list[dict[str, Any]]:
        """检查预算警告.

        Returns:
            警告列表,每个警告包含类型和消息
        """
        warnings = []

        # 检查日预算
        daily = self.get_daily_summary()
        if daily.total_cost >= self._budget_config.daily_budget * self._budget_config.warning_threshold:
            if daily.total_cost >= self._budget_config.daily_budget:
                warnings.append({
                    "type": "daily",
                    "level": "critical",
                    "message": f"日预算已超出! 已使用 ${daily.total_cost:.2f} / ${self._budget_config.daily_budget:.2f}",
                    "usage": daily.total_cost / self._budget_config.daily_budget,
                })
            else:
                warnings.append({
                    "type": "daily",
                    "level": "warning",
                    "message": f"日预算即将用尽: ${daily.total_cost:.2f} / ${self._budget_config.daily_budget:.2f}",
                    "usage": daily.total_cost / self._budget_config.daily_budget,
                })

        # 检查周预算
        weekly = self.get_weekly_summary()
        if weekly.total_cost >= self._budget_config.weekly_budget * self._budget_config.warning_threshold:
            if weekly.total_cost >= self._budget_config.weekly_budget:
                warnings.append({
                    "type": "weekly",
                    "level": "critical",
                    "message": f"周预算已超出! 已使用 ${weekly.total_cost:.2f} / ${self._budget_config.weekly_budget:.2f}",
                    "usage": weekly.total_cost / self._budget_config.weekly_budget,
                })
            else:
                warnings.append({
                    "type": "weekly",
                    "level": "warning",
                    "message": f"周预算即将用尽: ${weekly.total_cost:.2f} / ${self._budget_config.weekly_budget:.2f}",
                    "usage": weekly.total_cost / self._budget_config.weekly_budget,
                })

        # 检查月预算
        monthly = self.get_monthly_summary()
        if monthly.total_cost >= self._budget_config.monthly_budget * self._budget_config.warning_threshold:
            if monthly.total_cost >= self._budget_config.monthly_budget:
                warnings.append({
                    "type": "monthly",
                    "level": "critical",
                    "message": f"月预算已超出! 已使用 ${monthly.total_cost:.2f} / ${self._budget_config.monthly_budget:.2f}",
                    "usage": monthly.total_cost / self._budget_config.monthly_budget,
                })
            else:
                warnings.append({
                    "type": "monthly",
                    "level": "warning",
                    "message": f"月预算即将用尽: ${monthly.total_cost:.2f} / ${self._budget_config.monthly_budget:.2f}",
                    "usage": monthly.total_cost / self._budget_config.monthly_budget,
                })

        return warnings

    def set_budget_config(self, config: BudgetConfig) -> bool:
        """设置预算配置."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO budget_config
                    (id, daily_budget, weekly_budget, monthly_budget, warning_threshold, updated_at)
                    VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    config.daily_budget,
                    config.weekly_budget,
                    config.monthly_budget,
                    config.warning_threshold,
                ))
                conn.commit()
                self._budget_config = config
                return True
        except Exception as e:
            print(f"保存预算配置失败: {e}")
            return False

    def get_budget_config(self) -> BudgetConfig:
        """获取预算配置."""
        return self._budget_config

    def get_recent_records(self, limit: int = 50) -> list[CostRecord]:
        """获取最近的成本记录."""
        records = []
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM cost_records
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))

                for row in cursor.fetchall():
                    records.append(CostRecord.from_row(row))
        except Exception as e:
            print(f"获取最近记录失败: {e}")

        return records

    def export_report(self, format: str = "json", period: str = "monthly") -> str:
        """导出成本报告.

        Args:
            format: 报告格式 (json, csv, markdown)
            period: 报告周期 (daily, weekly, monthly, all_time)

        Returns:
            报告内容字符串
        """
        # 获取汇总数据
        if period == "daily":
            summary = self.get_daily_summary()
        elif period == "weekly":
            summary = self.get_weekly_summary()
        elif period == "monthly":
            summary = self.get_monthly_summary()
        else:
            summary = self.get_all_time_summary()

        budget = self.get_budget_config()

        if format == "json":
            report = {
                "period": period,
                "generated_at": datetime.now().isoformat(),
                "summary": summary.to_dict(),
                "budget": budget.to_dict(),
                "warnings": self.check_budget_warnings(),
            }
            return json.dumps(report, indent=2, ensure_ascii=False)

        elif format == "csv":
            lines = ["period,requests,input_tokens,output_tokens,total_tokens,total_cost"]
            lines.append(f"{summary.period},{summary.total_requests},{summary.total_input_tokens},"
                        f"{summary.total_output_tokens},{summary.total_tokens},{summary.total_cost}")
            return "\n".join(lines)

        elif format == "markdown":
            lines = [
                f"# 成本报告 - {period}",
                f"",
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"",
                f"## 汇总",
                f"",
                f"| 指标 | 数值 |",
                f"|------|------|",
                f"| 总请求数 | {summary.total_requests} |",
                f"| 输入Tokens | {summary.total_input_tokens:,} |",
                f"| 输出Tokens | {summary.total_output_tokens:,} |",
                f"| 总Tokens | {summary.total_tokens:,} |",
                f"| 总成本 | ${summary.total_cost:.4f} |",
                f"",
            ]

            if summary.model_breakdown:
                lines.extend([
                    f"## 模型细分",
                    f"",
                    f"| 模型 | 请求数 | Tokens | 成本 |",
                    f"|------|--------|--------|------|",
                ])
                for model, data in summary.model_breakdown.items():
                    lines.append(f"| {model} | {data['requests']} | {data['total_tokens']:,} | ${data['cost']:.4f} |")
                lines.append("")

            # 添加预算信息
            lines.extend([
                f"## 预算",
                f"",
                f"| 类型 | 预算 | 当前使用 | 使用率 |",
                f"|------|------|----------|--------|",
            ])

            if period == "daily":
                usage_pct = (summary.total_cost / budget.daily_budget * 100) if budget.daily_budget > 0 else 0
                lines.append(f"| 日预算 | ${budget.daily_budget:.2f} | ${summary.total_cost:.4f} | {usage_pct:.1f}% |")
            elif period == "weekly":
                usage_pct = (summary.total_cost / budget.weekly_budget * 100) if budget.weekly_budget > 0 else 0
                lines.append(f"| 周预算 | ${budget.weekly_budget:.2f} | ${summary.total_cost:.4f} | {usage_pct:.1f}% |")
            elif period == "monthly":
                usage_pct = (summary.total_cost / budget.monthly_budget * 100) if budget.monthly_budget > 0 else 0
                lines.append(f"| 月预算 | ${budget.monthly_budget:.2f} | ${summary.total_cost:.4f} | {usage_pct:.1f}% |")

            lines.append("")

            # 添加警告
            warnings = self.check_budget_warnings()
            if warnings:
                lines.extend([
                    f"## 警告",
                    f"",
                ])
                for w in warnings:
                    icon = "⚠️" if w["level"] == "warning" else "🚨"
                    lines.append(f"- {icon} {w['message']}")
                lines.append("")

            return "\n".join(lines)

        return ""

    def cleanup_old_records(self, days: int = 90) -> int:
        """清理旧记录."""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM cost_records WHERE timestamp < ?",
                    (cutoff.isoformat(),)
                )
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            print(f"清理旧记录失败: {e}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """获取统计信息."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) as count FROM cost_records")
                total_records = cursor.fetchone()["count"]

                cursor = conn.execute("SELECT COUNT(DISTINCT session_id) as count FROM cost_records")
                total_sessions = cursor.fetchone()["count"]

                db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

                return {
                    "total_records": total_records,
                    "total_sessions": total_sessions,
                    "db_path": str(self.db_path),
                    "db_size_bytes": db_size,
                    "db_size_mb": round(db_size / (1024 * 1024), 2),
                }
        except Exception as e:
            print(f"获取统计失败: {e}")
            return {
                "total_records": 0,
                "total_sessions": 0,
                "db_path": str(self.db_path),
                "db_size_bytes": 0,
                "db_size_mb": 0,
            }


# 全局成本追踪器实例
_global_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker(db_path: str = ".claude_costs.db") -> CostTracker:
    """获取全局成本追踪器实例."""
    global _global_cost_tracker
    if _global_cost_tracker is None:
        _global_cost_tracker = CostTracker(db_path)
    return _global_cost_tracker


def reset_cost_tracker() -> None:
    """重置全局成本追踪器实例."""
    global _global_cost_tracker
    _global_cost_tracker = None
