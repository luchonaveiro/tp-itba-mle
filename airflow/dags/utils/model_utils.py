import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from sklearn.metrics import mean_squared_error
import logging
from typing import Tuple, List

logger = logging.getLogger()


def evaluate_arima_model(X: np.array, arima_order: Tuple[int, int, int]) -> float:
    """
    Function to evaluate 1 ARIMA model

    Parameters:
    - X (np.array): numpy array containing the data to fit the ARIMA model
    - arima_order (Tuple[int, int, int]): tuple containing the ARIMA configuration

    Returns:
    - error (float): test set mean_squared_error after appliyng the ARIMA fitted model
    """

    # prepare training dataset
    train_size = int(len(X) * 0.66)
    train, test = X[0:train_size], X[train_size:]
    history = [x for x in train]
    # make predictions
    predictions = list()
    for t in range(len(test)):
        model = ARIMA(history, order=arima_order)
        model_fit = model.fit()
        yhat = model_fit.forecast()[0]
        predictions.append(yhat)
        history.append(test[t])
    # calculate out of sample error
    error = mean_squared_error(test, predictions)
    return error


def evaluate_arima_models(
    dataset: np.array, p_values: List[int], d_values: List[int], q_values: List[int]
) -> Tuple[int, int, int]:
    """
    Function to evaluate multiple ARIMA models and select the best parameters in terms of mean_squared_error

    Parameters:
    - dataset (np.array): numpy array containing the data to fit the ARIMA model
    - p_values (List[int]): list containing orders of the model for the autoregressive component
    - d_values (List[int]): list containing orders of the model for the difference component
    - q_values (List[int]): list containing orders of the model for the moving average component

    Returns:
    - best_cfg (Tuple[int, int, int]): tuple containing the best parameters in terms of mean_squared_error
    """
    dataset = dataset.astype("float32")
    best_score, best_cfg = float("inf"), None
    for p in p_values:
        for d in d_values:
            for q in q_values:
                order = (p, d, q)
                try:
                    mse = evaluate_arima_model(dataset, order)
                    if mse < best_score:
                        best_score, best_cfg = mse, order
                    logger.info("ARIMA%s MSE=%.3f" % (order, mse))
                except:
                    continue
    logger.info("Best ARIMA%s MSE=%.3f" % (best_cfg, best_score))
    return best_cfg
