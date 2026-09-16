from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.application import (
    Application,
    ApplicationDependency,
    ApplicationTool,
    Connection,
    DependencyTool,
)


class ApplicationRepository:
    @staticmethod
    def create(db: Session, **values) -> Application:
        item = Application(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list(db: Session) -> list[Application]:
        return list(db.scalars(select(Application).order_by(Application.name)).all())

    @staticmethod
    def get(db: Session, application_id: int) -> Application | None:
        return db.get(Application, application_id)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Application | None:
        return db.scalar(select(Application).where(Application.slug == slug))

    @staticmethod
    def get_by_name(db: Session, name: str) -> Application | None:
        return db.scalar(select(Application).where(Application.name == name))

    @staticmethod
    def update(db: Session, item: Application, **values) -> Application:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: Application) -> None:
        db.delete(item)
        db.commit()


class ConnectionRepository:
    @staticmethod
    def create(db: Session, **values) -> Connection:
        item = Connection(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list(db: Session) -> list[Connection]:
        return list(db.scalars(select(Connection).order_by(Connection.name)).all())

    @staticmethod
    def get(db: Session, connection_id: int) -> Connection | None:
        return db.get(Connection, connection_id)

    @staticmethod
    def update(db: Session, item: Connection, **values) -> Connection:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: Connection) -> None:
        db.delete(item)
        db.commit()


class ApplicationToolRepository:
    @staticmethod
    def create(db: Session, **values) -> ApplicationTool:
        item = ApplicationTool(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list_for_application(db: Session, application_id: int) -> list[ApplicationTool]:
        stmt = (
            select(ApplicationTool)
            .where(ApplicationTool.application_id == application_id)
            .order_by(ApplicationTool.priority, ApplicationTool.id)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get(db: Session, tool_id: int) -> ApplicationTool | None:
        return db.get(ApplicationTool, tool_id)

    @staticmethod
    def update(db: Session, item: ApplicationTool, **values) -> ApplicationTool:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: ApplicationTool) -> None:
        db.delete(item)
        db.commit()


class DependencyRepository:
    @staticmethod
    def create(db: Session, **values) -> ApplicationDependency:
        item = ApplicationDependency(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list_for_application(db: Session, application_id: int) -> list[ApplicationDependency]:
        stmt = select(ApplicationDependency).where(
            ApplicationDependency.application_id == application_id
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def get(db: Session, dependency_id: int) -> ApplicationDependency | None:
        return db.get(ApplicationDependency, dependency_id)

    @staticmethod
    def update(db: Session, item: ApplicationDependency, **values) -> ApplicationDependency:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: ApplicationDependency) -> None:
        db.delete(item)
        db.commit()


class DependencyToolRepository:
    @staticmethod
    def create(db: Session, **values) -> DependencyTool:
        item = DependencyTool(**values)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def list_for_dependency(db: Session, dependency_id: int) -> list[DependencyTool]:
        stmt = select(DependencyTool).where(DependencyTool.dependency_id == dependency_id)
        return list(db.scalars(stmt).all())

    @staticmethod
    def get(db: Session, dependency_tool_id: int) -> DependencyTool | None:
        return db.get(DependencyTool, dependency_tool_id)

    @staticmethod
    def update(db: Session, item: DependencyTool, **values) -> DependencyTool:
        for key, value in values.items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def delete(db: Session, item: DependencyTool) -> None:
        db.delete(item)
        db.commit()
