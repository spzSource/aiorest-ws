# -*- coding: utf-8 -*-
"""
    User model for authentication.
"""
__all__ = ('UserSQLiteModel', )

from sqlite3 import OperationalError

from aiorest_ws.auth.user.abstractions import User
from auth.user.utils import generate_password_hash
from aiorest_ws.auth.user.exceptions import RequiredModelFieldsNotDefined, \
    SearchCriteriaRequired, NotEnoughArguments
from aiorest_ws.auth.user.utils import SQL_CREATE_USER_TABLE, \
    SQL_CREATE_TOKEN_FOREIGN_KEY, SQL_USER_GET, SQL_USER_GET_BY_USERNAME, \
    SQL_USER_ADD, USER_MODEL_FIELDS, USER_MODEL_FIELDS_WITHOUT_PK, \
    SQL_USER_GET_WITH_ID, construct_update_sql, convert_user_raw_data_to_dict
from aiorest_ws.conf import settings
from aiorest_ws.db.backends.sqlite3.constants import IN_MEMORY
from aiorest_ws.db.backends.sqlite3.managers import SQLiteManager
from aiorest_ws.log import logger


class UserSQLiteModel(User):

    db_manager = SQLiteManager

    def __init__(self):
        super(UserSQLiteModel, self).__init__()
        db_path = settings.DATABASES['default']['name'] or IN_MEMORY
        db_manager = settings.DATABASES['default']['manager'] or None

        if db_manager:
            self.db_path = None
            self.db_manager = db_manager
        else:
            self.db_manager = self.db_manager(db_path)

        if db_path == IN_MEMORY:
            self.__create_models()

    def __create_models(self):
        try:
            self.db_manager.execute_script(SQL_CREATE_USER_TABLE)
            self.db_manager.execute_script(SQL_CREATE_TOKEN_FOREIGN_KEY)
        # This exception taken only in the case, when `user_id` foreign
        # keys already created. We didn't have any opportunity to check
        # existing column via SQL, because SQL syntax of SQLite is reduced.
        except OperationalError:
            pass

    def __user_defined_fields(self, init_data):
        overridden_fields = set(self.fields) & set(init_data.keys())
        user_defined_fields = {
            key: value
            for key, value in init_data.items()
            if key in overridden_fields
        }
        return user_defined_fields

    @property
    def fields(self):
        return USER_MODEL_FIELDS

    @property
    def fields_without_pk(self):
        return USER_MODEL_FIELDS_WITHOUT_PK

    def create_user(self, *args, **kwargs):
        if 'username' not in kwargs or 'password' not in kwargs:
            raise RequiredModelFieldsNotDefined(
                "Username and password fields are required"
            )

        kwargs['password'] = generate_password_hash(kwargs['password'])

        user_defined_fields = self.__user_defined_fields(kwargs)
        default_user_data = {
            'first_name': '',
            'last_name': '',
            'is_active': True,
            'is_superuser': False,
            'is_staff': False,
            'is_user': False,
        }

        default_user_data.update(user_defined_fields)
        user_data = [default_user_data[key] for key in self.fields_without_pk]

        try:
            self.db_manager.execute_sql(SQL_USER_ADD, user_data)
        except OperationalError as exc:
            logger.error(exc)

    def update_user(self, *args, **kwargs):
        username = kwargs.pop('username')
        if not username:
            raise SearchCriteriaRequired(
                "Username for WHEN statement is required."
            )

        if len(kwargs) < 1:
            raise NotEnoughArguments()

        if 'password' in kwargs.keys():
            kwargs['password'] = generate_password_hash(kwargs['password'])

        updated_fields = self.__user_defined_fields(kwargs)
        update_query, query_args = construct_update_sql(**updated_fields)
        query_args.append(username)
        try:
            self.db_manager.execute_sql(update_query, query_args)
        except OperationalError as exc:
            logger.error(exc)

    def get_user_by_username(self, username, with_id=False):
        try:
            if with_id:
                sql = SQL_USER_GET_WITH_ID
            else:
                sql = SQL_USER_GET_BY_USERNAME

            user_row = self.db_manager.execute_sql(
                sql, (username, )
            ).fetchone()
            if user_row:
                user_data = convert_user_raw_data_to_dict(user_row, with_id)
            else:
                user_data = {}
        except OperationalError as exc:
            logger.error(exc)
            user_data = {}
        return User(**user_data)

    def get_user_by_token(self, token):
        user_id = token['user_id']
        try:
            user_row = self.db_manager.execute_sql(
                SQL_USER_GET, (user_id, )
            ).fetchone()
            user_data = convert_user_raw_data_to_dict(user_row)
        except OperationalError as exc:
            logger.error(exc)
            user_data = {}
        return User(**user_data)
