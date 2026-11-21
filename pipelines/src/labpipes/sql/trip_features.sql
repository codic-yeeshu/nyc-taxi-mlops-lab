-- staging.trip_features for one month: the model's inputs and label (contracts/features.yaml), valid
-- trips only. Nothing known only after a trip is a column here; the feature_contract check enforces it.
-- {month} is substituted after validation (batch statements take no parameters).
create table if not exists staging.trip_features (
  trip_month      char(7)          not null,
  pickup_zone_id  integer          not null,
  dropoff_zone_id integer          not null,
  pickup_hour     smallint         not null,
  pickup_dow      smallint         not null,
  duration_min    double precision not null
) sortkey (trip_month);
delete from staging.trip_features where trip_month = '{month}';
insert into staging.trip_features
select trip_month, pickup_zone_id, dropoff_zone_id, pickup_hour, pickup_dow, duration_min
from staging.stg_trips
where trip_month = '{month}'
  and duration_min > 0 and duration_min <= 180
  and pickup_zone_id between 1 and 263 and dropoff_zone_id between 1 and 263
  and pickup_hour between 0 and 23 and pickup_dow between 0 and 6;
-- Historical distances for training the offline lookup. Kept apart from the model input table.
create table if not exists staging.trip_feature_distances (
  trip_month char(7) not null,
  pickup_zone_id integer not null,
  dropoff_zone_id integer not null,
  trip_distance double precision not null
) sortkey (trip_month);
delete from staging.trip_feature_distances where trip_month = '{month}';
insert into staging.trip_feature_distances
select trip_month, pickup_zone_id, dropoff_zone_id, trip_distance
from staging.stg_trips
where trip_month = '{month}'
  and duration_min > 0 and duration_min <= 180
  and pickup_zone_id between 1 and 263 and dropoff_zone_id between 1 and 263
  and pickup_hour between 0 and 23 and pickup_dow between 0 and 6
  and trip_distance > 0;
