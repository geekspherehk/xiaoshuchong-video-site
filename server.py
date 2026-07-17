#!/usr/bin/env python3
"""
小书虫视频工坊 — 订单接收服务器
接收前端表单提交，保存为 JSON 文件，并通知 Feishu
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# ── 配置 ──
HOST = "0.0.0.0"
PORT = 8877
DATA_DIR = Path(__file__).parent / "orders"
DATA_DIR.mkdir(exist_ok=True)

HKT = timezone(timedelta(hours=8))


def notify_feishu(order_data: dict):
    """通过 Feishu 发送通知给用户"""
    try:
        # 使用 Hermes send_message 工具发送通知
        # 由于不能直接调用 tool，我们写一条到日志 + 通过 cron 轮询
        name = order_data.get("name", "匿名")
        text_preview = order_data.get("content_text", "")[:50]
        plan = order_data.get("plan", "未指定")
        msg = (
            f"📦 **新订单 received!**\n"
            f"👤 {name}\n"
            f"📋 方案: {plan}\n"
            f"📝 文本预览: {text_preview}...\n"
            f"⏰ {order_data.get('created_at', '')}"
        )
        # 写入通知文件，供 cron 读取后发送
        notify_file = Path(__file__).parent / ".last_notification.json"
        notify_file.write_text(json.dumps(order_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[通知已写入] {msg}")
    except Exception as e:
        print(f"[通知失败] {e}")


@app.route("/api/submit", methods=["POST"])
def submit_order():
    """接收前端提交的订单"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "message": "无法解析 JSON 数据"}), 400

    # 必填字段校验
    name = (data.get("name") or "").strip()
    contact = (data.get("contact") or "").strip()
    content_text = (data.get("content_text") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "请填写名字"}), 400
    if not contact:
        return jsonify({"status": "error", "message": "请填写联系方式"}), 400
    if not content_text:
        return jsonify({"status": "error", "message": "请填写文本内容"}), 400

    # 构造订单
    now = datetime.now(HKT)
    order = {
        "id": now.strftime("%Y%m%d_%H%M%S"),
        "name": name,
        "contact": contact,
        "video_type": data.get("video_type", "read-aloud"),
        "plan": data.get("plan", "single"),
        "content_text": content_text,
        "notes": (data.get("notes") or "").strip(),
        "voice_preference": (data.get("voice_preference") or "auto").strip(),
        "show_bilingual": data.get("show_bilingual", True),
        "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
    }

    # 保存到文件
    file_path = DATA_DIR / f"{order['id']}.json"
    file_path.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")

    # 写入最新订单标记（供 Hermes cron 读取）
    latest = DATA_DIR / ".latest.json"
    latest.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"[新订单] {order['id']} - {name}")
    print(f"[文本] {content_text[:80]}...")
    print(f"[方案] {order['plan']}")
    print(f"{'='*60}\n")

    # 通知 Feishu
    notify_feishu(order)

    return jsonify({
        "status": "success",
        "message": "订单已收到！我确认后会尽快联系你开始制作。",
        "order_id": order["id"],
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "orders_count": len(list(DATA_DIR.glob("*.json")))})


@app.route("/api/orders", methods=["GET"])
def list_orders():
    """列出订单（供检查用）"""
    orders = []
    for f in sorted(DATA_DIR.glob("*.json"), reverse=True):
        if f.name.startswith("."):
            continue
        try:
            orders.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return jsonify({"orders": orders, "total": len(orders)})


if __name__ == "__main__":
    print(f"🐛 小书虫订单服务器启动中...")
    print(f"   http://{HOST}:{PORT}")
    print(f"   POST /api/submit  — 提交订单")
    print(f"   GET  /api/health  — 健康检查")
    print(f"   GET  /api/orders  — 订单列表")
    app.run(host=HOST, port=PORT, debug=False)
