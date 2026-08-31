import os
import logging
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from sqlalchemy import Column, Integer, String, Text, DateTime, create_engine, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('notification-service')

DB_USER = os.getenv('DB_USER', 'devops')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'devops123')
DB_NAME = os.getenv('DB_NAME', 'taskdb')
DATABASE_URL = os.getenv('DATABASE_URL', f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@db:5432/{DB_NAME}_notification')
TASK_SERVICE_URL = os.getenv('TASK_SERVICE_URL', 'http://task-service:8000')
HEALTH_CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', '30'))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False)
    notif_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(50), default='sent')
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine)


@app.before_request
def start_health_check():
    pass


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'notification-service',
        'timestamp': datetime.now(timezone.utc).isoformat()
    }), 200


@app.route('/notify', methods=['POST'])
def create_notification():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    task_id = data.get('task_id')
    notif_type = data.get('type', 'generic')
    message = data.get('message', '')
    if not task_id or not message:
        return jsonify({'error': 'task_id and message are required'}), 400
    notification = Notification(
        task_id=task_id,
        notif_type=notif_type,
        message=message,
        status='sent'
    )
    db = SessionLocal()
    try:
        db.add(notification)
        db.commit()
        # Save values before closing session
        notif_id = notification.id
        notif_task_id = notification.task_id
        notif_type_val = notification.notif_type
        notif_message = notification.message
        notif_status = notification.status
        notif_created = notification.created_at
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create notification: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()
    logger.info(f'Notification sent: task_id={task_id}, type={notif_type}, message={message}')
    return jsonify({
        'id': notif_id,
        'task_id': notif_task_id,
        'type': notif_type_val,
        'message': notif_message,
        'status': notif_status,
        'created_at': notif_created.isoformat()
    }), 201


@app.route('/notifications', methods=['GET'])
def get_notifications():
    db = SessionLocal()
    try:
        # SQLAlchemy 2.x: use select() instead of query()
        stmt = select(Notification).order_by(Notification.created_at.desc())
        notifications = db.execute(stmt).scalars().all()
        result = [{
            'id': n.id,
            'task_id': n.task_id,
            'type': n.notif_type,
            'message': n.message,
            'status': n.status,
            'created_at': n.created_at.isoformat()
        } for n in notifications]
    finally:
        db.close()
    return jsonify(result)


@app.route('/notifications/<int:notification_id>', methods=['GET'])
def get_notification(notification_id):
    db = SessionLocal()
    try:
        # SQLAlchemy 2.x: use session.get() instead of query().get()
        notification = db.get(Notification, notification_id)
        if not notification:
            return jsonify({'error': 'Notification not found'}), 404
        result = {
            'id': notification.id,
            'task_id': notification.task_id,
            'type': notification.notif_type,
            'message': notification.message,
            'status': notification.status,
            'created_at': notification.created_at.isoformat()
        }
    finally:
        db.close()
    return jsonify(result)


@app.route('/notifications/task/<int:task_id>', methods=['GET'])
def get_notifications_by_task(task_id):
    db = SessionLocal()
    try:
        stmt = select(Notification).filter_by(task_id=task_id).order_by(Notification.created_at.desc())
        notifications = db.execute(stmt).scalars().all()
        result = [{
            'id': n.id,
            'task_id': n.task_id,
            'type': n.notif_type,
            'message': n.message,
            'status': n.status,
            'created_at': n.created_at.isoformat()
        } for n in notifications]
    finally:
        db.close()
    return jsonify(result)


@app.route('/notifications/stats', methods=['GET'])
def get_notification_stats():
    db = SessionLocal()
    try:
        # SQLAlchemy 2.x: use select(func.count()) instead of query().count()
        total = db.execute(select(Notification)).scalars().all()
        total_count = len(total)
        sent = db.execute(select(Notification).filter_by(status='sent')).scalars().all()
        sent_count = len(sent)
        failed = db.execute(select(Notification).filter_by(status='failed')).scalars().all()
        failed_count = len(failed)
    finally:
        db.close()
    return jsonify({'total': total_count, 'sent': sent_count, 'failed': failed_count})


@app.route('/', methods=['GET'])
def dashboard():
    return open('/app/dashboard.html').read()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
