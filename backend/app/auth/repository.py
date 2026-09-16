from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.user import User


class UserRepository:
    @staticmethod
    def create(db: Session, **values) -> User:
        item = User(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def get(db: Session, user_id: int) -> User | None:
        return db.get(User, user_id)

    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        return db.scalar(select(User).where(User.username == username))

    @staticmethod
    def list(db: Session) -> list[User]:
        return list(db.scalars(select(User).order_by(User.username)).all())

    @staticmethod
    def count(db: Session) -> int:
        return len(UserRepository.list(db))

    @staticmethod
    def update(db: Session, item: User, **values) -> User:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: User) -> None:
        db.delete(item)
        db.commit()
