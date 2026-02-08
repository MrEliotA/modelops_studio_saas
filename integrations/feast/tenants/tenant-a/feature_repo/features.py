from datetime import timedelta
from feast import Entity, FeatureView, Field
from feast.data_source import PushSource
from feast.types import Float32, Int64
from feast.value_type import ValueType

driver = Entity(
    name="driver",
    join_keys=["driver_id"],
    value_type=ValueType.INT64,
    description="Driver entity",
)

driver_stats_push_source = PushSource(
    name="driver_stats_push_source",
)

driver_stats_fv = FeatureView(
    name="driver_stats_fv",
    entities=[driver],
    ttl=timedelta(days=1),
    schema=[
        Field(name="avg_daily_trips", dtype=Int64),
        Field(name="conv_rate", dtype=Float32),
        Field(name="acc_rate", dtype=Float32),
    ],
    online=True,
    source=driver_stats_push_source,
)
