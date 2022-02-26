CREATE TABLE IF NOT EXISTS airport_daily_summary (
    date timestamp NOT NULL,
    origin_airport varchar(10) NOT NULL,
    average_dep_delay float,
    flights integer,
    dep_delay_anomaly integer,
    dep_delay_pred float,
    dep_delay_higher_ci float,
    dep_delay_lower_ci float,
    PRIMARY KEY (date, origin_airport)
);

