from django.utils.functional import lazy
from feedly.structures.hash import BaseRedisHashCache
from feedly.structures.list import BaseRedisListCache
import logging
logger = logging.getLogger(__name__)


class RedisSortedSetCache(BaseRedisListCache, BaseRedisHashCache):
    key_format = 'redis:sorted_set_cache:%s'
    sort_asc = False

    def count(self):
        '''
        Returns the number of elements in the sorted set
        '''
        key = self.get_key()
        redis_result = self.redis.zcount(key, '-inf', '+inf')
        #lazily convert this to an int, this keeps it compatible with distributed connections
        redis_count = lambda: int(redis_result)
        lazy_factory = lazy(redis_count, int, long)
        lazy_object = lazy_factory()
        return lazy_object

    def add_many(self, value_score_pairs):
        '''
        value_key_pairs
        '''
        key = self.get_key()
        results = []

        def _add_many(redis, value_score_pairs):
            for value, score in value_score_pairs:
                logger.debug('adding to %s with value %s and score %s',
                             key, value, score)
                result = redis.zadd(key, value, score)
                results.append(result)

        #start a new map redis or go with the given one
        self._map_if_needed(_add_many, value_score_pairs)

        return results

    def remove_many(self, values):
        '''
        values
        '''
        key = self.get_key()
        results = []

        def _remove_many(redis, values):
            for value in values:
                logger.debug('removing value %s from %s', value, key)
                result = redis.zrem(key, value)
                results.append(result)

        #start a new map redis or go with the given one
        self._map_if_needed(_remove_many, values)

        return results

    def remove_by_scores(self, scores):
        key = self.get_key()
        results = []

        def _remove_many(redis, scores):
            for score in scores:
                logger.debug('removing score %s from %s', score, key)
                result = redis.zremrangebyscore(key, score, score)
                results.append(result)

        #start a new map redis or go with the given one
        self._map_if_needed(_remove_many, scores)

        return results

    def contains(self, value):
        '''
        Uses zscore to see if the given activity is present in our sorted set
        '''
        key = self.get_key()
        result = self.redis.zscore(key, value)
        activity_found = bool(result)
        return activity_found

    def size(self):
        '''
        Returns an approximate size of the sorted set
        '''
        size = 0
        results = RedisSortedSetCache.get_results(self, 0, -1)
        for serialized, score in results:
            size += len(serialized)
            size += len(unicode(score))
        return size

    def trim(self, max_length=None):
        '''
        Trim the sorted set to max length
        zremrangebyscore
        '''
        key = self.get_key()
        if max_length is None:
            max_length = self.max_length

        # map things to the funny redis syntax
        end = (max_length * -1) - 1

        removed = self.redis.zremrangebyrank(key, 0, end)
        logger.info('cleaning up the sorted set %s to a max of %s items' %
                    (key, max_length))
        return removed

    def get_results(self, start=None, stop=None):
        '''
        Retrieve results from redis using zrevrange
        O(log(N)+M) with N being the number of elements in the sorted set and M the number of elements returned.
        '''
        if stop is None or start is None:
            start = None

        if self.sort_asc:
            redis_range_fn = self.redis.zrange
        else:
            redis_range_fn = self.redis.zrevrange

        # python [:2] gives 2 results, redis zrange 0:2 gives 3, so minus one
        redis_stop = stop
        if redis_stop is not None:
            redis_stop -= 1

        key = self.get_key()
        redis_results = redis_range_fn(key, start, redis_stop, withscores=True)

        return redis_results
