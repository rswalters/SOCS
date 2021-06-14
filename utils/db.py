import sqlalchemy as db
import os
import yaml
from astropy.time import Time
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import MetaData, create_engine
import sys
import pandas as pd

Base = declarative_base()

if sys.version_info > (3,):
    long = int


def _id_from_time():
    """Generate an id from the current time of format YYYYMMDDHHMMSSsss"""
    time = Time.now()
    id = time.iso
    id = id.replace('-', '').replace(' ', '').replace(':', '').replace('.', '')
    return long(id)


class dbconnect:
    """Simple connection to the pharos database"""

    def __init__(self) -> None:
        super().__init__()

        SR = os.path.abspath(os.path.dirname(__file__) + '/../')

        with open(os.path.join(SR, 'config', 'sedm_config.yaml')) as data_file:
            self.config = yaml.load(data_file, Loader=yaml.FullLoader)

        self.db_connect = self.config['pharosdb']['dbstring']
        self.connect = create_engine(self.db_connect)

        self.meta = MetaData()
        self.meta.reflect(bind=self.connect)

        self.request_table = self.meta.tables['requests']
        self.object_table = self.meta.tables['object']

    def get_dataframe_query(self, query):
        """Return a pandas dataframe from a query"""

        try:
            return pd.read_sql_query(query, self.connect)
        except Exception as e:
            print(str(e))
            return False

    def update_status_request(self, status, request_id):
        """
        Update the status request in the pharos database

        :param status:
        :param request_id:
        :return:
        """

        update_statement = self.request_table.update() \
            .where(self.request_table.columns.id == request_id) \
            .values(status=status)

        return self.connect.execute(update_statement)

    def create_request(self, request_dict):
        """
        Update the status request in the pharos database

        :param request_dict:

        :return:
        """
        id = _id_from_time()

        aggs = self.request_table.insert().values(id=id, **request_dict)
        print(self.connect.execute(aggs))

        return id

    def get_object_id(self, name):
        """
        Search for the object id of a target by the name
        :param name:
        :return:
        """

        check_id = db.select([self.request_table.columns.id]).where(self.request_table.columns.name == name)
        ret = self.connect.execute(check_id).fetchall()

        return ret[0]


