### `Hello, World` with AWS Lambda

##### Why:

To get you some hands-on experience with real serverless stuff, and with performance data collection/simple analysis/representation.

##### What to do:

- deploy a simple serverless Java 11 application locally and in the cloud;
- write a Python script to call the application many times and do some stat analysis over collected performance data.

##### How to do:

Follow this tutorual to craft the simples "Hello, World" application for AWS Lambda:
https://awstip.com/aws-sam-sam-local-java-serverless-application-82ba03de2c5e

Modify the application to do smth faster than what the original `Hello, World` does (like return current date/time as I did in the example) to get rid of all the internal overheads.

Try to run it locally as the tutorial states, with `sam local start-api`.

You can query the application/function with your browser or with a comand like `curl` (in Linux). So you can write a Python script which will run the query, say, 20-30 times (for local runs, as it's slow) and ~1000 runs for cloud deployments, time the execution latency and plot the spectrum. Then you can invoke it, say 20-30 times with different intervals (1min, 2min, 5min), and compare the latency graphs to observe the cold start (this will take a while to run).

##### Extra references:
https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-getting-started-hello-world.html
