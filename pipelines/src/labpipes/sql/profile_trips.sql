-- Read-only profile of a validated month in Redshift. The three-hour bound
-- matches the given mart's filter. Check thresholds are decided separately.
with month_rows as (
  select *
  from staging.stg_trips
  where trip_month = '{month}'
), distinct_rows as (
  select distinct *
  from month_rows
)
select
  count(*) as rows,
  count(*) - (select count(*) from distinct_rows) as duplicate_rows,
  count(case when pickup_at is null or dropoff_at is null then 1 end) as null_timestamps,
  count(case when passenger_count is null then 1 end) as null_passengers,
  count(case when duration_min <= 0 then 1 end) as nonpositive_duration,
  count(case when duration_min > 180 then 1 end) as over_3h,
  count(case when pickup_zone_id is null or pickup_zone_id not between 1 and 263
               or dropoff_zone_id is null or dropoff_zone_id not between 1 and 263 then 1 end) as unknown_zone,
  count(case when trip_distance < 0 then 1 end) as negative_distance
from month_rows;
