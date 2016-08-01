import time

import bson
import pymongo
import pytest

from jaraco.mongodb import oplog
from jaraco.mongodb import service


class TestReplacer:
	def test_rename_index_op_ns(self):
		"""
		As an index operation references namespaces,
		when performing a rename operation, it's also important
		to rename the ns in the op itself.
		"""
		op = {
			'ts': bson.Timestamp(1446495808, 3),
			'ns': 'airportlocker.system.indexes',
			'op': 'i',
			'o': {
				'ns': 'airportlocker.luggage.chunks',
				'key': {'files_id': 1, 'n': 1},
				'name': 'files_id_1_n_1', 'unique': True
			},
		}

		ren = oplog.Renamer.from_specs("airportlocker=airportlocker-us")
		ren(op)

		assert op['ns'] == 'airportlocker-us.system.indexes'
		assert op['o']['ns'] == 'airportlocker-us.luggage.chunks'


@pytest.fixture
def replicable_instance(request):
	"""
	Return a MongoDB instance (distinct from the normal
	fixture) configured for replication such that it has
	an oplog.
	"""
	try:
		r_set = service.MongoDBReplicaSet()
		r_set.log_root = ''
		r_set.start()
		r_set.get_connection()
		request.addfinalizer(r_set.stop)
	except Exception as err:
		pytest.skip("MongoDB not available ({err})".format(**locals()))
	return r_set


class TestOplogReplication:
	def test_index_deletion(self, replicable_instance, mongodb_instance):
		"""
		A delete index operation should be able to be applied to a replica
		"""
		source = replicable_instance.get_connection()
		dest = mongodb_instance.get_connection()
		source.index_deletion_test.stuff.ensure_index("foo")
		dest.index_deletion_test.stuff.ensure_index("foo")
		source_oplog = oplog.Oplog(source.local.oplog.rs)
		# need to sleep one second to ensure that the
		# creation operation is less than begin_ts.
		time.sleep(1)
		begin_ts = bson.Timestamp(int(time.time()), 0)
		source.index_deletion_test.stuff.drop_index("foo_1")
		delete_index_op, = source_oplog.since(begin_ts)
		oplog.apply(dest, delete_index_op)
		only_index, = dest.index_deletion_test.stuff.list_indexes()
		assert only_index['name'] == '_id_'
