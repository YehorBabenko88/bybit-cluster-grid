"""Strict bounded UTC representation codecs; no float epoch conversion."""
from datetime import datetime,timedelta,timezone
import re

MAX_EPOCH_MS=253402300799999
_EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)
_UNIT=timedelta(milliseconds=1)

def epoch_milliseconds(value):
    if type(value) is str:
        if re.fullmatch('0|[1-9][0-9]{0,14}',value) is None:raise ValueError('canonical bounded millisecond clock required')
        value=int(value)
    if type(value) is not int or not 0<=value<=MAX_EPOCH_MS:raise ValueError('bounded nonboolean millisecond clock required')
    return value

def utc_from_epoch_milliseconds(value):
    return _EPOCH+timedelta(milliseconds=epoch_milliseconds(value))

def epoch_milliseconds_from_utc(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset()!=timedelta(0):raise ValueError('exact aware UTC datetime required')
    result,remainder=divmod(value-_EPOCH,_UNIT)
    if remainder!=timedelta(0):raise ValueError('submillisecond datetime cannot become a millisecond cursor')
    return epoch_milliseconds(result)
