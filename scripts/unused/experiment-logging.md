### Usual configs:
- *Hardware:* xl170 (3 workers, 1 master)
- *Functions:* `fibonacci-python`, `hotel-app-geo`, `hotel-app-user`, `hotel-app-profile`, `video-analytics`
- *RPS limits:* 
	- `fibonacci-python`: 100-1000
	- `hotel-app-geo`: 100-1000
	- `hotel-app-user`: 100-1000
	- `hotel-app-profile`: 100-1000
	- `video-analytics`: 5-50
### Experiment from before 2023-09-19, 21:34
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* 60s-180s
- *Total time:* N/A
- *Delta:* 60s
#### Notes:
-  Replicas failed to exceed 1 for non-video-analytics
	- video-analytics had low replica counts (<5)
- video-analytics often failed to invoke (<1 real RPS)
- CPU utilization never exceeded 100%
- Memory utilization showed more variance
- Lower metric collection failure than prior experiments with lower duration limits or lower deltas
### Experiment from 2023-09-19, 21:34
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* 30s-120s
- *Total time:* N/A
- *Delta:* 60s
#### Notes:
- Functions arrive quite slowly
- video-analytics still dysfunctional, despite Running status in `kubectl get pods`
- Replicas still stuck on 1.
- Going to try lower delta, then increased amount of benchmarks
### Experiment from 2023-09-19, 21:49
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* 30s-120s
- *Total time:* 
- *Delta:* 30s
#### Notes:
- Replicas still stuck on 1
- Real RPS often falls significantly short of RPS target
- Fibonacci and hotel-app functions have real RPS in the range (150, 450).

### Update: figured out why Replicas stuck on 1.
In an earlier commit, the requests and limits for each function were modified to be equal. As a result, a container could never use over 100% of its requested resources, which meant the scaler would never detect a sufficiently high usage to scale up.

In addition, the limit on resource usage prevented benchmarks from running at higher RPS values--especially video-analytics, which requires lots of resources. This is why it was returning real RPS values of 0.74, etc.
### Experiment from 2023-09-19, 23:16
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual, but video-analytics is set to range(5,10)
- *Duration limits:* 30s-120s
- *Total time:* N/A
- *Delta:* 75s
#### Notes:
- In this experiment, we will increase the CPU requests and limits of video-analytics, since previous data has shown it constantly exceeding the default 250Mi CPU setting.
- We will also change the upper RPS bound for video-analytics to 10 RPS, since this is sufficiently demanding of resources already.
- Each node has 20 CPU cores.
	- Recog will have requests=1000Mi, limits=4000Mi
	- Streaming will have requests=250Mi, limits=1000Mi
	- Decoder will have requests=1000Mi, limits=2000Mi
- These numbers at the moment are somewhat arbitrary. We need to find a better way to figure out requests and limits for each function. Perhaps this is something that can be learned.
	- To collect additional data on this, we will add each function's limits and requests to the table as well.

### Experiment from 2023-09-19, 23:59
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual, but video-analytics is (5, 10)
- *Duration limits:* (60s, 120s)
- *Total time:* 24h
- *Delta:* 90s
#### Notes:
-  Metrics errors are significantly reduced, likely thanks to more generous resource allocations
- 5-10 RPS for video-analytics has turned out to be very reasonable
- However, there is still insufficient diversity of resource usage, especially for streaming and decoder
	- For now, I think we can just look at non-video-analytics, since the chained aspect makes it difficult
	- We can still run video-analytics with current settings to give more realism (stress the nodes), but priority will be fibonacci and hotel-app
- For fibonacci and hotel-app, there is also not enough diversity in resource usage, especially memory
	- Could increase target RPS to exert higher stress; however:
		  ![[Pasted image 20230920235548.png]]
		  The data suggests that the target RPS vs. delta RPS relationship is probably not linear, but more likely polynomial or exponential. As target RPS increases, delta RPS will increase faster, so it doesn't make much sense to keep pushing target RPS beyond 1000.
	- Instead, it's probably better to change CPU/memory requests and limits to fit the functions. More specifically, the HPA's algorithm should seek to keep total CPU utilization and number of replicas proportional. That is, when a function's CPU total utilization increases N-fold, the replicas should increase N-fold accordingly. 
		- CPU utilization data from using previous specs: ![[Pasted image 20230921000403.png]]
		  Most of the replica counts are clustered around 3-6, while most of the CPU utils are around 50-150%. Looking at the trendline, we see 100% CPU utilization is typically obtained at around 4 replicas. If we want to expand the replica range, we need to decrease the CPU request value for the functions. Here, it seems reasonable to divide request value by 4 so that most replica counts will be around 12-24.
		- Memory utilization data: ![[Pasted image 20230921000848.png]]
		  Most of the memory utilizations are very low (between 0% and 5%). There appear to be few points because most of them are overlapping. The memory request value should probably be divided by ~16 to give more variance. Replica count here is most likely just a result of CPU scaling, rather than memory scaling.
	- Looking at the data, it seems reasonable to make the following changes:
		- CPU requests: 250m --> 60m
		- Memory requests: 1024Mi --> 64Mi
	- Limits can stay the same, because they aren't large enough to cause problems.
	- For `hotel-app` functions and for `fibonacci-python`, we will now use the following resource specs: 
	  ![[Pasted image 20230921001356.png]]

### Experiment from 2023-09-21, 00:20
#### Configs:
- *Hardware:* usual
- *Functions:* usual, but we changed the resource specs. See notes in previous experiment.
- *RPS limits:* same as previous
- *Duration limits:* same as previous
- *Total time:* 
- *Delta:* same as previous
#### Notes:
- Experiment failed after containers timed out
	- Logs showed that containers were pending
	- Likely due to too many pods (each node has a limit of 110 pods)
	- Last experiment had functions with up to 35 replicas
	- For next experiment, we should:
		- Set maxReplicas to 100
		- Have less functions running simultaneously
			- We can do this by increasing interval time. Perhaps avoid having overlapping functions in general, since we are not interested in stressing nodes yet
- Restarted nodes to fix this issue.
### Experiment from 2023-09-22, 09:56
#### Configs:
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* 
- *Total time:* 
- *Delta:* 
#### Notes:
- This experiment will attempt to expand the data collection (not including video-analytics for now).
- We proceed as follows:
1. Read the DataFrame from the HPA data file.
2. Clean the data.
3. For each row in the DataFrame:
	1. Read the replica recommendation and evaluate the scale range. Here, we can set the exact number of values in the range to test. 
	2. Read the invocation specs: duration, RPS.
	3. For every value N in scale range:
		1. Create a new process
		2. Deploy benchmark.
			1. Read the benchmark name
			2. Create the duplicate yaml without HPA and set replicas to N
			3. Deploy
		3. Invoke the benchmark with its assigned duration and RPS.
		4. Collect data
	4. Join the processes created in the loop so that we wait until it finishes executing.
- The total number of pods needed to run the function for all scale values concurrently is defined by the function $$\frac{1}{2}\left(\operatorname{ceil}\left(0.7x\right)\ +\ \operatorname{floor}\left(1.3x\right)\right)\ \cdot\left(\operatorname{floor}\left(1.3x\right)\ -\operatorname{ceil}\left(0.7x\right)+1\right).$$This cannot exceed 330, which is the max pods total across the three worker nodes. We would actually set a limit of 300 pods to allow built-in pods to run as well. From this equation, the maximum replica recommendation we could look at is 23 replicas.
  
  It is possible, however, to increase step size so that we don't examine every replica value. For instance, we could just examine 5-7 uniform values maximum instead for each range.

### Experiment from 2023-09-23, 00:40
#### Configs:
- *Experiment type:* expanded data collection
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* N/A
- *Total time:* N/A
- *Delta:* N/A
#### Notes:
- We are running the expanded data collection with the following configs:
	- n-runs = 1
	- n-values = 6
	- percent-range = 20
- The data being expanded on is `didxdgrlda`, which contains 792 entries.
	- 102 are video-analytics
	- 690 are non-video-analytics
- If the average benchmark takes up to 120s:
	- This will take 690 x 120s = 23h
- The data_processing for expanded data collection still needs to be fixed.
- There is also still an issue of pods sticking around even after they're supposed to be deleted.
	- May be related to this:
	  ![[Pasted image 20230923005008.png]]

Created: 2023-09-19 21:27
### Experiment from 2023-09-23, 13:52
#### Configs:
- *Experiment type:* expanded data collection
- *Hardware:* usual
- *Functions:* usual
- *RPS limits:* usual
- *Duration limits:* N/A
- *Total time:* estimated 23h
- *Delta:* N/A
#### Notes:
- Rerun of previous experiment, this time with safeguard against Prometheus metric collecting failure
- Heatmaps suggest some correlations between important variables; however, linear correlations are still imperfect
- There is an issue, however, regarding the Pearson correlation. It seems to be over-sensitive to outliers: see the plot of Replicas vs. Memory:![[Pasted image 20230923135331.png]]
  Here, it seems that the ~1600% memory utilization data point is messing up the correlation calculation.  
## References
1. 

## Tags
