from sqlalchemy.orm import Session

from . import models, schemas


def get_apk_details(db: Session, apk_id: int = None, apk_name: str = None):
    return db.query(models.APKDetails).filter(models.APKDetails.apk_name == apk_name).first() if apk_name is not None else db.query(models.APKDetails).filter(models.APKDetails.id == apk_id).first()

def get_first_apk_details(db: Session):
    return db.query(models.APKDetails).order_by(models.APKDetails.id.desc()).first()


def get_all_apk_details(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.APKDetails).offset(skip).limit(limit).all()


def create_apk_details_item(db: Session, item: schemas.APKDetailsCreate):
    db_item = models.APKDetails(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


def set_device_icon(db: Session, device_id: str, col: str, icon: str, text: str):
    instance = db.query(models.DeviceInfo).filter_by(device_id=device_id).first()
    if not instance:
        instance = models.DeviceInfo(device_id=device_id)
        db.add(instance)
    if col != 'none':
        instance.col = col
    if col != 'none':
        instance.icon = icon
    instance.text = text
    db.commit()


def get_device_decorations(db: Session, device_id: str):
    instance = db.query(models.DeviceInfo).filter_by(device_id=device_id).first()
    if not instance:
        return None
    return {'col': instance.col, 'icon': instance.icon, 'text': instance.text}


def _get_settings(db: Session):
    instance = db.query(models.Settings ).first()
    if not instance:
        instance = models.Settings()
        db.add(instance)
        db.commit()
    return instance

def update_settings(db, screen_updates: int):
    instance = _get_settings(db)
    instance.screen_updates = screen_updates
    db.commit()

def crud_defaults(db: Session, so_far):
    instance = _get_settings(db)
    so_far['screen_updates'] = instance.screen_updates
