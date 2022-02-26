import pandas as pd
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_model_results(data: pd.DataFrame, airport: str) -> plotly.graph_objects.Figure:
    """
    Function that returns the timeseries plot of the desired airport average delay time,
    with the anomalies distinguished from the normal values,
    with the CI calculated with the model

    Parameters:
    - data (pandas.DataFrame): containing ds, y, y_pred, yhat_lower, yhat_upper
    - airport (string): airport code to plot

    Returns:
    - fig (plotly.graph_objs._figure.Figure): time series plot
    """

    anomaly_values = data.query("dep_delay_anomaly == 1")
    normal_values = data.query("dep_delay_anomaly == 0")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add traces
    fig.add_trace(
        go.Scatter(
            x=anomaly_values["ds"],
            y=anomaly_values["y"],
            name=f"Anomaly",
            mode="markers",
            line_color="red",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=normal_values["ds"],
            y=normal_values["y"],
            name=f"Normal Value",
            mode="markers",
            line_color="blue",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data["ds"],
            y=data["yhat"],
            name=f"Forecasted",
            line_color="lightblue",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data["ds"],
            y=data["yhat_lower"],
            name=f"Forecasted (LI)",
            fill="tonexty",
            line_color="lightblue",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=data["ds"],
            y=data["yhat_upper"],
            name=f"Forecasted (UI)",
            fill="tonexty",
            line_color="lightblue",
        )
    )

    # Update figure layout
    fig.update_layout(
        title_text=f"<b>{airport} - Average Departure Delay</b> <br><sup>Using a 80% CI ARIMA Model.</sup>",
        template="plotly_white",
        hovermode="x",
        xaxis_showgrid=False,
        yaxis_showgrid=False,
    )

    fig.update_xaxes(showgrid=False, zeroline=True)
    fig.update_yaxes(showgrid=False, zeroline=True)

    return fig


def plot_number_of_flights(
    data: pd.DataFrame, airport: str
) -> plotly.graph_objects.Figure:
    """
    Function that returns the timeseries plot of the desired airport amount of flights per day,
    with the days considered as an anomaly average delay time distinguished from the normal days,

    Parameters:
    - data (pandas.DataFrame): containing ds, count, dep_delay_anomaly
    - airport (string): airport code to plot

    Returns:
    - fig (plotly.graph_objs._figure.Figure): time series plot
    """
    anomaly_values = data.query("dep_delay_anomaly == 1")
    normal_values = data.query("dep_delay_anomaly == 0")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # Add traces
    fig.add_trace(
        go.Bar(
            x=anomaly_values["ds"],
            y=anomaly_values["count"],
            name=f"Anomaly Average DEP_DELAY",
            marker_color="red",
        )
    )
    fig.add_trace(
        go.Bar(
            x=normal_values["ds"],
            y=normal_values["count"],
            name=f"Normal Average DEP_DELAY",
            marker_color="blue",
        )
    )

    # Update figure layout
    fig.update_layout(
        title_text=f"<b>{airport} - Amount of Daily Flights</b> <br><sup>Anomaly DEP_DELAY values detected using a 80% CI ARIMA Model.</sup>",
        template="plotly_white",
        hovermode="x",
        xaxis_showgrid=False,
        yaxis_showgrid=False,
    )

    fig.update_xaxes(showgrid=False, zeroline=True)
    fig.update_yaxes(showgrid=False, zeroline=True)

    return fig
