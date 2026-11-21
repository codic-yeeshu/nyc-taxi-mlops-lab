-- The last approved version of each month, storing only the mart's inputs and sort key.
create table if not exists staging.mart_ready_trips (
  trip_month char(7) not null,
  pickup_at timestamp,
  pickup_zone_id integer,
  pickup_hour smallint,
  duration_min double precision
) diststyle auto sortkey (pickup_at);
delete from staging.mart_ready_trips where trip_month = '{month}';
insert into staging.mart_ready_trips
select trip_month, pickup_at, pickup_zone_id, pickup_hour, duration_min
from staging.stg_trips
where trip_month = '{month}';
