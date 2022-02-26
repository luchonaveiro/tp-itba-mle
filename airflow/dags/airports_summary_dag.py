"""Airports DAG."""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from airflow.sensors.s3_key_sensor import S3KeySensor

from sqlalchemy.exc import IntegrityError
from sqlite_cli import SqLiteClient

import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA

import boto3

from utils.model_utils import evaluate_arima_models
from utils.plot_utils import plot_model_results, plot_number_of_flights

# Set up Logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


DB_CONNECTION = BaseHook.get_connection("airports_db")
DB_URI = DB_CONNECTION.get_uri()

GRID_SEARCH_BEST_ARIMA_PARAMETERS = False
DEFAULT_ARIMA_PARAMETERS = (5, 1, 1)

S3_DATA_BUCKET = "com.lucianonaveiro.itba.tp.airport.data"
S3_OUTPUT_PLOTS_BUCKET = "com.lucianonaveiro.itba.tp.airport.plots"


def _calculate_daily_dep_delay(**context):
    year = str(context["data_interval_start"].year)
    s3_client = boto3.client("s3")
    s3_client.download_file(
        S3_DATA_BUCKET,
        f"{year}.csv",
        f"/tmp/data_{year}.csv",
    )
    logger.info(f"File {year}.csv download from {S3_DATA_BUCKET} S3 bucket")

    data = pd.read_csv(f"/tmp/data_{year}.csv")

    logger.info(f"{year}.csv loaded ok")

    logger.info("Processing data...")
    model_data = (
        data.groupby(["FL_DATE", "ORIGIN"])["DEP_DELAY"]
        .agg(["mean", "count"])
        .reset_index(drop=False)
    )
    model_data["ds"] = model_data["FL_DATE"]
    model_data["y"] = model_data["mean"]

    origins = model_data.ORIGIN.unique()

    for origin in origins:
        model_airport_data = model_data.query(f"ORIGIN=='{origin}'")
        model_airport_data = model_airport_data.sort_values(by="FL_DATE")

        if len(model_airport_data) > 2:
            logger.info(f"Fitting ARIMA Model to {origin}...")
            X = model_airport_data["y"].values
            if GRID_SEARCH_BEST_ARIMA_PARAMETERS:
                p_values = [0, 1, 2, 4, 5, 6, 8, 10]
                d_values = [0, 1, 2]
                q_values = [0, 1, 2]
                best_arima_params = evaluate_arima_models(
                    X, p_values, d_values, q_values
                )
                model = ARIMA(X, order=best_arima_params)
            else:
                model = ARIMA(X, order=DEFAULT_ARIMA_PARAMETERS)

            model_fit = model.fit()
            logger.info(f"ARIMA Model to {origin} fitted")

            logger.info(f"Processing {origin} output data...")
            forecast = model_fit.get_prediction()
            prediction = forecast.predicted_mean
            ci = forecast.conf_int(0.2)

            model_airport_data["yhat"] = prediction
            model_airport_data["yhat_lower"] = ci[:, 0]
            model_airport_data["yhat_upper"] = ci[:, 1]

            model_airport_data["yhat_lower"] = [
                max(x, np.percentile(model_airport_data["yhat_lower"], 1))
                for x in model_airport_data["yhat_lower"]
            ]
            model_airport_data["yhat_upper"] = [
                min(x, np.percentile(model_airport_data["yhat_upper"], 99))
                for x in model_airport_data["yhat_upper"]
            ]

            model_airport_data["dep_delay_anomaly"] = 0
            model_airport_data.loc[
                (model_airport_data["yhat_lower"] > model_airport_data["y"])
                | (model_airport_data["yhat_upper"] < model_airport_data["y"]),
                "dep_delay_anomaly",
            ] = 1

            logger.info(f"Generating {origin} output plots...")
            plot_trends = plot_model_results(model_airport_data, origin)
            plot_trends.write_image(
                f"/tmp/{origin}_daily_average_delay_departure.png",
                width=1500,
                height=800,
            )

            plot_flights = plot_number_of_flights(model_airport_data, origin)
            plot_flights.write_image(
                f"/tmp/{origin}_daily_flights.png",
                width=1500,
                height=800,
            )

            logger.info(
                f"Uploading {origin} output plots to {S3_OUTPUT_PLOTS_BUCKET} S3 bucket..."
            )
            s3_client.upload_file(
                f"/tmp/{origin}_daily_average_delay_departure.png",
                S3_OUTPUT_PLOTS_BUCKET,
                f"{year}/{origin}/daily_average_delay_departure.png",
            )

            s3_client.upload_file(
                f"/tmp/{origin}_daily_flights.png",
                S3_OUTPUT_PLOTS_BUCKET,
                f"{year}/{origin}/daily_flights.png",
            )

            export_data = model_airport_data[
                [
                    "ds",
                    "ORIGIN",
                    "y",
                    "count",
                    "dep_delay_anomaly",
                    "yhat",
                    "yhat_upper",
                    "yhat_lower",
                ]
            ]
            export_data = export_data.rename(
                columns={
                    "ds": "date",
                    "ORIGIN": "origin_airport",
                    "y": "average_dep_delay",
                    "count": "flights",
                    "yhat": "dep_delay_pred",
                    "yhat_upper": "dep_delay_higher_ci",
                    "yhat_lower": "dep_delay_lower_ci",
                }
            )
            export_data.to_csv(
                f"/tmp/{origin}_summarize.csv",
                index=False,
            )
            logger.info(f"Data and plots form {origin} exported OK")

            sql_cli = SqLiteClient(DB_URI)
            try:
                logger.info(
                    f"Inserting {origin} values ({len(export_data)}) for {year}..."
                )
                sql_cli.insert_from_frame(export_data, "airport_daily_summary")
            except IntegrityError:
                logger.info(f"Already have {origin} values for {year} on DB")
            except Exception as e:
                logger.info(f"Unknown error: {e}")

    logger.info("Cleaning up dir...")
    os.remove(f"/tmp/data_{year}.csv")
    os.remove(f"/tmp/{origin}_daily_average_delay_departure.png")
    os.remove(
        f"/tmp/{origin}_daily_flights.png",
    )
    os.remove(f"/tmp/{origin}_summarize.csv")


default_args = {"owner": "luciano.naveiro"}

with DAG(
    "airports_daily_summary_dag",
    schedule_interval="@annually",
    start_date=datetime(2009, 1, 1),
    # start_date=datetime(2016, 1, 1),
    catchup=True,
    max_active_runs=1,
    default_args=default_args,
) as dag:
    calculate_daily_dep_delay = PythonOperator(
        task_id="calculate_daily_dep_delay",
        python_callable=_calculate_daily_dep_delay,
        retries=3,
        retry_delay=timedelta(seconds=90),
    )

calculate_daily_dep_delay
