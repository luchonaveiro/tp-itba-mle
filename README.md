# **TP Final Machine Learning Engineering**


![flujo de trabajo de ejemplo](https://github.com/luchonaveiro/tp-itba-ml/actions/workflows/deploy_s3.yml/badge.svg)

The objective of the following project is to build an ETL capable of processing the [Airlines Delay and Cancellation Data from 2009-2018](https://www.kaggle.com/yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018?select=2009.csv), to detect the anomalies on the average of the daily departure delay for each airport.

The ETL is developed using Apache Airflow which extracts the raw data from S3; process it, applies an ARIMA model, and stores the data on a database created on an RDS instance; where Apache Superset is connected to visualize the results. A scalable infrastructire is deployed to enable all this:
- implementation of a [*Managed Workflows for Apache Airflow* environment (MWAA)](https://aws.amazon.com/managed-workflows-for-apache-airflow/), where the model will run to detect the airport's departure delya anomalies. To detect an anomaly, an [ARIMA](https://www.statsmodels.org/devel/generated/statsmodels.tsa.arima.model.ARIMA.html) model is used, and the threshold to split a normal observation of an anomaly, is a confidence interval of th 80%, calculated by the same ARIMA model.
- deployment of a [PostgreSQL RDS instance](https://aws.amazon.com/rds/), where the daily summarized values are going to be stored.
- deployment of [Apache Superset](https://superset.apache.org/), which connects to the database created on the RDS instance and generates a dahsboard to visualize:
    - the number of daily flights of each airport, indicating the days considered as an anomaly regarding the departure delay
    - the average departure delay of each airport, together with the expected value and the 80% CI returned by the ARIMA model


## **Airports Data**

AGREGAR LOS COMANDOS PARA DESCARGAR DE KAGGLE Y SUBIR A S3

As I comented previously, the data refers to the airlines Ddelay and cancellation flights from 2009-2018, and once downloaded, I upload them on `com.lucianonaveiro.itba.tp.airport.data` S3 bucket.

After uploading them, I deploy all the infrastructure


## **AWS Infrastructure**
First I create some S3 buckets, and copy my local files to AWS:
- `airflow-itba-tp.lucianonaveiro`: where the `dags` and `requirements.txt` file are stored
- `com.lucianonaveiro.itba.tp.cloudformation`: where I store some large CloudFormation templates
- `com.lucianonaveiro.itba.tp.airport.plots`: where I store the ouptut files from the ETL process executed by Apache Airflow

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-S3 \
  --template-file infraestructura/cloudformation/01_s3.yaml

$ aws s3 cp --recursive airflow/dags s3://airflow-itba-tp.lucianonaveiro/dags/
$ aws s3 cp airflow/requirements/requirements.txt s3://airflow-itba-tp.lucianonaveiro/requirements.txt

```

Afer this, I execute the template that builds the VPC where all the services and resources created for this project are going to run:

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-VPC \
  --template-file infraestructura/cloudformation/02_vpc.yaml \
  --capabilities CAPABILITY_IAM
```

Once the VPC is created, I deploy both the MWAA and Apache Superset. For the latter one, I base on the following [Quick Start Reference Deployment](https://aws-quickstart.github.io/quickstart-apache-superset/).

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-AIRFLOW \
  --template-file infraestructura/cloudformation/03_managed_airflow.yaml \
  --capabilities CAPABILITY_IAM

$ aws cloudformation deploy \
  --stack-name TP-ITBA-SUPERSET \
  --template-file infraestructura/cloudformation/04_superset.yaml \
  --s3-bucket com.lucianonaveiro.itba.tp.cloudformation \
  --s3-prefix superset \
  --capabilities CAPABILITY_IAM
```

Once the stacks finished creating, I deploy the RDS instance. This instance is not available from the public internet: only MWAA, Apache Superset and an EC2 instance I deploy to run the `db/init.sql` script (by using the `UserData` on the CloudFormation template, to create the `airport_daily_summary` table inside the RDS instance), have access to it.

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-RDS \
  --template-file infraestructura/cloudformation/05_rds.yaml \
  --capabilities CAPABILITY_IAM
```

When all the stacks are created, I look on CloudFormation AWS Console for the Apache Airflow URL, the Apache Superset URL and the RDS endpoint, on the output of each stack 


![image](assets/aws_cloudformation.png)

Just to visualize it, this is the whole infrastruture created by the CloudFormation stacks, to develop the ETL:

![image](assets/aws_infra.png)


## **Apache Airflow**
The first thing to do when MWAA is running, is to create the connection to the RDS instance, under the name of `airports_db`.

![image](assets/airflow_db_connection.png)

Once created the connection, I can turn on the `airports_daily_summary` DAG, which has an annual schedule with a backfill from 2009 to execute the ETL for all the necessary years.

![image](assets/airflow_running.png)

The DAG is in charge of:
- downloading the raw data from `com.lucianonaveiro.itba.tp.airport.data` S3 bucket
- process the data generating a daily timeseries for each airport 
- run the ARIMA model to each timeseries,finding the days where the departure delay is quite different as normal
- store the daily summarized table on the table created on the RDS instance
- generate 2 plots for each airport and store them on `com.lucianonaveiro.itba.tp.airport.plots` S3 bucket. The plots explain the following:
    - number of dialy flights for each airport, indicating the days with anomalies.
    - expected values and 80% CI vs the observed average departure delay, to understand the decision of the model when splitting between normal and days with anomalies.

The DAG executes all these steps for each year from 2009 to 2018.

On the following plots, we can see the data from the *ANC* airport from 2013, where we can see clearly the days with strange average departure delay, are quite off the 80% CI from the ARIMA model.

![image](assets/airflow_ANC_daily_average_delay_departure.png)
![image](assets/airflow_ANC_daily_flights.png)

In case of executing twice the same year from Apache Airflow, the data does not duplicate on the table inside the RDS instance, since the combination of date and airport is defined as primary key, and the `IntegrityError` exception is managed, so neither the data is duplicated, nor the code is going to break.


## **ARIMA Model**
As I explained previously, to split between normal and days with anomalies, I fit an ARIMA model to the daily average departure delay for each airport (for each year) and compare the obersved average, with the 80% CI returned by the ARIMA model. 

ARIMA, short for *Auto Regressive Integrated Moving Average* is actually a class of models that explains a given time series based on its own past values, that is, its own lags and the lagged forecast errors, so that equation can be used to forecast future values.

An ARIMA model is characterized by three terms:
- `p` is the order of the *Auto Regressive* (AR) term. It refers to the number of lags of Y to be used as predictors.
- `q` is the order of the *Moving Average* (MA) term. It refers to the number of lagged forecast errors that should go into the ARIMA Model.
- `d` is the number of differencing required to make the time series stationary

An ARIMA model is one where the time series was differenced at least once to make it stationary and you combine the AR and the MA terms. So the equation becomes:

![image](assets/arima_formula.png)

On this project, to select the optimum values of `p`, `q` and `d` for each time series, a Grid Search approach was selected (using 66% of the data as training an the rest as test), where the selected values are the ones that minimizes the error.

As the problem is one of a time series, the order of tha data points matter, so the split between training and test set is ont random, instead we do a nested approach, where I iterate the 33% test data, predicting only one day at a time, so at the end of the process I compare all the single pedictions with the test array to get the final error.

![image](assets/arima_nested_cross_validation.png)


## **Apache Superset**
Once that the DAG ran for all the airports for all the years, storing the summarized data on the PostrgeSQL RDS table, I can start using Apache Superset and connect it to the DB 

![image](assets/superset_db_connection.png)

When the connection is created, I can define a dataset pointing to the `airport_daily_summary` table created on the RDS instance. While creating the dataset, i am going to define 2 new dimensions `date` (is the same `date` as the DB, but in timestamp) and `dep_delay_anomaly_label` (is just a map `dep_delay_anomaly` to visualize it clearly on the dashabord)

![image](assets/superset_dataset_creation.png)
![image](assets/superset_dataset_creation_2.png)
![image](assets/superset_dataset_creation_3.png)

Having Apache Superset connected to the PostgreSQL DB, I can create the dashboards with the same plots as the DAG stored on `com.lucianonaveiro.itba.tp.airport.plots` S3 bucket, along with 2 filters: one for date and the other for the airport.

To accomplish these we have to build 3 charts (`Charts -> + Chart (Button)`). First we will build the `Amount of Flights` plot, where we select the dataset we want to use (`public.airport_daily_summary`) and the visualization type (`Time-series Chart`).

![image](assets/superset_explanation_1.png)

Now, on the `Data` section, we have just to select the date column, the metric we want to plot and how we are going to break it down. Here I chose to break down the amout of daily flights by the flag `dep_delay_anomaly`, which is the flag created with ARIMA model to detect the days with anomalies.

![image](assets/superset_explanation_2.png)

On the `Customize` section, I just enable the legend to be displayed, and stacked the daily values.

![image](assets/superset_explanation_3.png)

For the second plot, the one displaying the predicted average departure delay vs the observed value, together with the CI, we choose the same dataset and visualization type as the previuos one, but we add more metrics, on per each series we want to plot.

![image](assets/superset_explanation_4.png)

Last, for the filter, we also create a chart with the same dataset as teh previous, but with a `Filter box` as the visualization type. Here we choose the `date` and `origin_airport` columns to be filtered.

When the dashboard is set up, I can filter the year 2013 and the *ANC* airport and find the same insights as on the plots stored on S3.

![image](assets/superset_results_1.png)
![image](assets/superset_results_2.png)

## **CI/CD**
I also implemented a *CI/CD Pipeline* using GitHub Actions (the workflow named `deploy_s3.yml`), which on each pull and merge to the main branch, it uploads the `airflow/dags` directory and the `airflow/requirements.txt` file to the `airflow-itba-tp.lucianonaveiro` S3 bucket.

To correctly implement this, I create an IAM User with an attached policy to be able to upload and delete files to the `airflow-itba-tp.lucianonaveiro` S3 bucket:

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-GHA-IAM \
  --template-file infraestructura/cloudformation/06_gha_iam.yaml \
  --capabilities CAPABILITY_IAM
```

On the outputs pane of this stack, both the `ACCESS_KEY_ID` and the `SECRET_ACCESS_KEY` can be found. These two values are necessary to create the *Secrets* on GitHub Actions settings

![image](assets/github_actions.png)





----------



El objetivo del siguiente trabajo es detectar las anomalias de las demoras de salidas de los vuelos diarios de cada aeropuerto para los [siguientes datos](https://www.kaggle.com/yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018?select=2009.csv). 
Estos datos describen las demoras y cancelaciones de distintos aeropuertos desde el 2009 al 2018.
Para lograrlo, se desarrolla un ETL en Apache Airflow que extrae los datos desde S3, los procesa y los guarda en una instancia de RDS a la que se conecta Apache Superset para visualizar los resultados. Para realizar todo esto, se despliega una infraestructura escalable donde:
- se implementa un ambiente de *Managed Apache Airflow* donde va a correr el modelo que detecta las anomalias dentro de los promedios diarios de las demoras de salidas para cada año y aeropuerto. Para distinguir entre un dia normal y un dia anomalo, se usa un modelo [ARIMA](https://www.statsmodels.org/devel/generated/statsmodels.tsa.arima.model.ARIMA.html) con un intervalo de confianza del 80%, por lo que si un dia, el promedio de las demoras de salidas esta por fuera del intervalo, se considera como un dia anomalo.
- se levanta una instancia de RDS de PostgreSQL para guardar los datos diarios umarizados.
- se despliega Apache Superset, que se conecta a la instancia de RDS levantada y se genera un dashboard para visualizar:
    - la cantidad de vuelos diarios de cada aeropuerto, marcando los dias considerados anomalos.
    - el promedio diario de demora de salida de cada aeropuerto, junto con el valor esperado y un intervalo de confianza del 80% generado por el modelo ARIMA, para entender los valores anomalos.

## **Datos de los Aeropuertos**
Como comente previamente, los datos se refieren a las demoras y cancelaciones de distintos aeropuertos desde el 2009 al 2018.
Los datos a utilizar se encuentran en el siguiente sitio de [Kaggle](https://www.kaggle.com/yuanyuwendymu/airline-delay-and-cancellation-data-2009-2018?select=2009.csv), donde los descargo y los subo al bucket `com.lucianonaveiro.itba.tp.airport.data` de S3.

Una vez que tengo los datos en ese bucket de S3, levanto toda la infraestructura para resolver el problema.

## **Infraestructura en AWS**
Primero creo algunos buckets en S3, y copio los archivos de mi computadora a AWS. Los buckets que creo son los siguientes:
- `airflow-itba-tp.lucianonaveiro`: donde se van a guardar los DAGs y archivo `requirements.txt` con las librerias necesarias para correrlos
- `com.lucianonaveiro.itba.tp.cloudformation`: donde guardo algunos templates que superan los 50kb
- `com.lucianonaveiro.itba.tp.airport.plots`: donde guardo los graficos que genera el ETL en Apache Airflow.  

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-S3 \
  --template-file infraestructura/cloudformation/01_s3.yaml

$ aws s3 cp --recursive airflow/dags s3://airflow-itba-tp.lucianonaveiro/dags/
$ aws s3 cp airflow/requirements.txt s3://airflow-itba-tp.lucianonaveiro/requirements.txt

```

Luego ejecuto el `yaml` que crea la VPC donde van a correr todos los servicios y recursos que voy a crear en este trabajo:

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-VPC \
  --template-file infraestructura/cloudformation/02_vpc.yaml \
  --capabilities CAPABILITY_IAM
```

Una vez creada la VPC, puedo levantar tanto el MWAA como Apache Superset, para desplegar Apache Superset me baso en el siguiente [Quick Start Reference Deployment](https://aws-quickstart.github.io/quickstart-apache-superset/):

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-AIRFLOW \
  --template-file infraestructura/cloudformation/03_managed_airflow.yaml \
  --capabilities CAPABILITY_IAM

$ aws s3 cp infraestructura/cloudformation/04_superset.yaml \
  s3://com.lucianonaveiro.itba.tp.cloudformation/vpc_rds_airflow_superset.yaml

$ aws cloudformation deploy \
  --stack-name TP-ITBA-SUPERSET \
  --template-file infraestructura/cloudformation/04_superset.yaml \
  --s3-bucket com.lucianonaveiro.itba.tp.cloudformation \
  --s3-prefix superset \
  --capabilities CAPABILITY_IAM
```

Una vez que terminaron de desplegarse, creo la instancia de RDS. Esta instancia no esta disonible desde la internet publica, y solo tienen acceso MWAA, Apache Superset, y una instancia de EC2 que voy a utilizar para correr un script para crear la base de datos dentro de la instancia (eso esta dentro del `UserData` en el archivo `yaml`)

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-RDS \
  --template-file infraestructura/cloudformation/05_rds.yaml \
  --capabilities CAPABILITY_IAM
```

Una vez que este todo levantado, me dirigo a CloudFormation dentro de la Consola de AWS, y busco la URL de Apache Airflow, la URL de Apache Superset, y la URL de la instancia de RDS (que voy a conectar tanto en Apache Airflow como en Apache Superset)

PONER PRINT DE LOS OUTPUTS DE CLOUDFORMATION

Luego de ejecutar todos estos comandos, CloudFormation nos crea los siguientes recursos en AWS

PONER DIAGRAMA DE LA INFRAESTRUCTURA

## **Apache Airflow**
Lo primero que hago una vez levantado MWAA, es crear la conexion a la instancia de RDS con el nombre de `airports_db`, ya que el codigo del DAG busca esa conexion

PONER PRINT DE LA CREACION DE LA CONEXION A LA DB

Una vez creada la conexion, ya se puede prender el DAG, que tiene un schedule anual, y un backfill desde 2009 para correr el ETL para todos los años presentes en los datos. 

El DAG se encarga de descargar los datos del bucket `com.lucianonaveiro.itba.tp.airport.data`, resumirlos diariamente para cada aeropuerto, correr un modelo ARIMA para ajustar un modelo sobre los promedios de demora de salida diarios, pudiendo detectar los dias con valores distintos a lo esperado, guardar los resultados en la instancia de RDS, y generar 2 graficos y guardarlos en el bucket `com.lucianonaveiro.itba.tp.airport.plots` de S3:
- cantidad de vuelos diarios por año y aeropuerto, marcando los dias considerados anomalos.
- las predicciones e intervalos de confianza del 80% vs los valores reales, para entender la decision del modelo a la hora de marcar un dia como anomalo.

Aca se pueden ver los dos graficos para el año XXXX y el aeropuerto XXX, donde se ve claramente como las anomalias se encuentran fuera del intervalo de confianza generado por el modelo ARIMA

PONER 2 GRAFICOS DE ALGUN AÑO Y AEROPUERTO

Es importante remarcar que en caso de ejecutar dos veces algun año desde Apache Airflow, la data no se duplica ya que la excepcion de `IntegrityError` esta manejada en el DAG y no duplica datos ni rompe la ejecucion.

## **Modelo ARIMA**
Como mencione previamente, para separar entre un dia anomalo y un dia normal, ajusto un modelo ARIMA de los tiempos de demora promedio para cada año y cada aeropuerto, y si el valor observado se encuentra por fuera del intervalo de confianza del 80% que devuelve el modelo, lo considero como un dia anomalo.

PONER DESCRIPCION PIOLA DEL ARIMA

Es importante mencionar que el modelo ARIMA depende de tres parametros: `p`, `d` y `q`, donde:
- `p`: orden del componente autorregresivo del modelo
- `d`: orden del componente integrado del modelo
- `q`: orden del componente de la media movil del modelo

Para encontrar los valores optimos para cada año y aeropuerto, implemente un *Grid Search* donde recorro distintas combinaciones de valores, y elijo el que minimiza el error. La particularidad de estos modelos de series de tiempo, es que 

## **Apache Superset**
Una vez que corrio todo el DAG, guardando los datos diarios sumarizados en la base de datos creada dentro de la instancia de RDS, para todos los años de 2009 a 2018 para todos los aeropuertos, ingreso a Apache Superset y lo conecto a esa base de datos.

PONER PRINT DE LA CONEXION A LA DB

Teniendo la conexion creada, se puede crear el dashboard que replica los mismos graficos que se guardaron en el ETL en S3, pero de una manera mas dinamica, pudiendo filtrar el aeropuerto y las fechas. 

PONER VIDEO O PRINTS DE TODOS LOS PASOS

Habiendo creado el dashbaord, podemos filtrar el año XXXX y el aeropuerto XXX, y vemos el mismo grafico que se guardaron en la seccion de *Apache Airflow*.

## **CI/CD**
Tambien se agrego un *CI/CD* mediante GitHub Actions (el workflow llamando `deploy_s3.yml`), que en cada push o merge?? (probar esto) al main branch, se suben los DAGs y el archivo requirements.txt a S3. Para poder implementar esto, se crea un usuario y se le agrega una policy especifica para poder subir archivos al bucket `airflow-itba-tp.lucianonaveiro` de S3: 

```
$ aws cloudformation deploy \
  --stack-name TP-ITBA-GHA-IAM \
  --template-file infraestructura/cloudformation/06_gha_iam.yaml \
  --capabilities CAPABILITY_IAM
```

En los outputs del stack en CloudFormation, se encuentran el `ACCESS_KEY_ID` y `SECRET_ACCESS_KEY` que uso para crear las crear los *Secrets* en GitHub.

PONER PRINT DE COMO SETEO LAS CREDENCIALES EN GITHUB

-----
-1) aws s3 sync modelo/data s3://com.lucianonaveiro.itba.tp.airport.data

0) breve explicacion de lo que se quiere lograr

1) download data from kaggle

2) upload data to S3
    aws s3 sync raw/ s3://BUCKET/tp

3) execute cloudformation for airflow bucket
    aws cloudformation deploy \
    --stack-name TP-ITBA-S3 \
    --template-file infraestructura/cloudformation/01_s3.yaml ---- 30s

    aws s3 cp infraestructura/cloudformation/04_superset.yaml s3://com.lucianonaveiro.itba.tp.cloudformation/vpc_rds_airflow_superset.yaml

4) upload dags and requirements.txt
    aws s3 cp --recursive airflow/dags s3://airflow-itba-tp.lucianonaveiro/dags/
    aws s3 cp airflow/requirements.txt s3://airflow-itba-tp.lucianonaveiro/requirements.txt

5) execute cloudformation for the rest of the things
    aws cloudformation deploy \
    --stack-name TP-ITBA-VPC \
    --template-file infraestructura/cloudformation/02_vpc.yaml \
    --capabilities CAPABILITY_IAM \
    --parameters ParameterKey=EnvironmentName,ParameterValue=TP-ITBA ParameterKey=ClusterName,ParameterValue=supersetOnAWS (NO) ---- 5min

    aws cloudformation deploy \
    --stack-name TP-ITBA-AIRFLOW \
    --template-file infraestructura/cloudformation/03_managed_airflow.yaml \
    --capabilities CAPABILITY_IAM \
    --parameters ParameterKey=EnvironmentName,ParameterValue=TP-ITBA ParameterKey=ClusterName,ParameterValue=supersetOnAWS (NO) ---- 30min

    aws cloudformation deploy \
    --stack-name TP-ITBA-SUPERSET \
    --template-file infraestructura/cloudformation/04_superset.yaml \
    --s3-bucket com.lucianonaveiro.itba.tp.cloudformation \
    --s3-prefix superset \
    --capabilities CAPABILITY_IAM \
    --parameters ParameterKey=EnvironmentName,ParameterValue=TP-ITBA ParameterKey=ClusterName,ParameterValue=supersetOnAWS (NO) ---- 7min

    aws cloudformation deploy \
    --stack-name TP-ITBA-RDS \
    --template-file infraestructura/cloudformation/05_rds.yaml \
    --capabilities CAPABILITY_IAM \
    --parameters ParameterKey=EnvironmentName,ParameterValue=TP-ITBA ParameterKey=ClusterName,ParameterValue=supersetOnAWS (NO) --- 8min

6) add connection to RDS on airflow (agregar print tambien)

7) prints de los graficos que guarda en S3

8) contar que agregue un github actions para que deploye automaticamente cualquier cambio en dags o requirements.txt

9) explicacion del ARIMA y de que esta haciendo

10) add connection to RDS on superset (agregar print tambien)

11) creo tabla como dataset en superset

12) prints de como se arman los plots para el dashbaord

13) prints de los dashboards creados en superset

14) diagrama final de toda la infraestructura