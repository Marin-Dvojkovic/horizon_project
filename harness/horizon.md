

## Horizon: Scalable Dependency-driven Data Cleaning
## El Kindi Rezig
## MIT CSAIL
elkindi@csail.mit.edu
## Mourad Ouzzani
## Qatar Computing Research Institute
mouzzani@hbku.edu.qa
## Walid G. Aref
## Purdue University
aref@cs.purdue.edu
## Ahmed K. Elmagarmid
## Qatar Computing Research Institute
aelmagarmid@hbku.edu.qa
## Ahmed R. Mahmood
## Purdue University
amahmoo@cs.purdue.edu
## Michael Stonebraker
## MIT CSAIL
stonebraker@csail.mit.edu
## ABSTRACT
A large class of data repair algorithms rely on integrity constraints
to detect and repair errors. A well-studied class of constraints is
Functional Dependencies (FDs, for short). Although there has been
an increased interest in developing general data cleaning systems
for a myriad of data errors, scalability has been left behind. This is
because current systems assume data cleaning is performed offline
and in one iteration. However, developing data science pipelines
is highly iterative and requires efficient cleaning techniques to
scale to millions of records in seconds/minutes, not days. In our
efforts to re-think the data cleaning stack and bring it to the era
of data science, we introduceHorizon, an end-to-end FD repair
system to address two key challenges: (1) Accuracy: Most existing
FD repair techniques aim to produce repairs that minimize changes
to the data that may lead to incorrect combinations of attribute
values (or patterns).Horizonleverages the interaction between
the data patterns induced by the various FDs, and subsequently
selects repairs that preserve the most frequent patterns found in
the original data, and hence leading to a better repair accuracy.
(2) Scalability: Existing data cleaning systems struggle when dealing
with large-scale real-world datasets.Horizonfeatures a linear-time
repair algorithm that scales to millions of records, and is orders-
of-magnitude faster than state-of-the-art cleaning algorithms. A
benchmark ofHorizonagainst state-of-the-art cleaning systems
on multiple datasets and metrics shows thatHorizonconsistently
outperforms existing techniques in repair quality and scalability.
PVLDB Reference Format:
## El Kindi Rezig, Mourad Ouzzani, Walid G. Aref, Ahmed K. Elmagarmid,
Ahmed R. Mahmood, and Michael Stonebraker. Horizon: Scalable
Dependency-driven Data Cleaning. PVLDB, 14(11): 2546 - 2554, 2021.
doi:10.14778/3476249.3476301
## 1  INTRODUCTION
Current data cleaning systems do not scale well with large datasets.
The reason is that they are designed to support one-shot and offline
data cleaning. However, emerging data science applications pose
new scalability requirements that current data cleaning systems
do not deliver. In light of our collaborations with data scientists
This work is licensed under the Creative Commons BY-NC-ND 4.0 International
License. Visit https://creativecommons.org/licenses/by-nc-nd/4.0/ to view a copy of
this license. For any use beyond those covered by this license, obtain permission by
emailing info@vldb.org. Copyright is held by the owner/author(s). Publication rights
licensed to the VLDB Endowment.
Proceedings of the VLDB Endowment, Vol. 14, No. 11 ISSN 2150-8097.
doi:10.14778/3476249.3476301
## 0.1
## 1
## 10
## 100
## 1000
## 10000
## 100000
20k40k60k80k100k1M2M16M32M64M
## Runtime (sec)
## #tuples
## Horizon
## HOLISTIC
## SAMP
HoloClean
## Baran
## Unified
Figure 1:Runtime of state-of-the-art cleaning systems vs.Horizon
at several organizations, we observe that (1) Data preparation for
large datasets takes the bulk of the human effort; (2) Specificity:
Because it is important to know the input/output of each stage
in the pipeline to facilitate debugging, various data preparation
tools are loosely connected to address specific problems in the data
(e.g., inputting missing values). Because it is hard to debug, data
scientists rarely use a one-box data cleaning system that strives to
clean all types of data errors [16,26]; (3) Iterativeness: Developing
data science pipelines is highly iterative and data scientists run
their pipelines dozens of time to refine them [29].
In response to the above observations, we envision that building
data cleaning systems that are tailored to specific data errors, as op-
posed to general-purpose data cleaning systems, is more amenable
to efficient implementations and is easier to debug and tune. As a
result, our approach to data cleaning is to re-think common data
quality problems and build scalableby designtechniques to address
them. The importance of scalability of data cleaning in a data sci-
ence setting is twofold: (1) Support larger datasets, and (2) Allow
data scientists to refine their pipelines by enabling faster workflow
iterations. Following this direction, we develop a data cleaning sys-
tem for a specific, yet common, data inconsistency problem, namely,
functional dependency violations, that is efficientby design.
A functional dependency (FD)푋→푌defined over a relation
푅that has attributes푋and푌states that records sharing the same
value in푋must share the same value in푌(e.g.,푧푖푝→푠푡푎푡푒).
FDs are some of the most fundamental and well-studied integrity
constraints. This is because their syntax is easy to understand
and they can be expressed in a variety of languages (e.g., SQL).
Additionally, they form the basis for more expressive rules, e.g.,
Conditional FDs (CFDs) [17] and Denial Constraints (DCs) [10].
Although extensive efforts have been proposed to clean dirty
data, the focus has mainly been on supporting more error types
rather than on developing scalable solutions to existing data quality
problems [24,25]. Case in point, it still takes hours/days to even
## 2546

cidprovider_id
provider_
address
provider_
area_id
service_
area
1GF903140 W Court0212
2GF903140 W Court0212
## 3GF903
## 1407 Wescam
## Court
## T75212
## 4YT43
## 1407 Wescam
## Court
## T75212
## 5YT43
## 1407 Wescam
## Court
## T75212
6RG09160 Asher StT75212
fd
## 1
: provider_id → provider_address
fd
## 2
: provider_address → provider_area_id
fd
## 3
: provider_area_id → service_area
Functional dependencies (횺)
Build FD pattern graph (Section 3)
Project FDs on dirty data
Assess quality of each FD pattern
FDs static analysis (Section 4, 5)
Determine attribute boundness (sec. 4)
Devise traversal order on FD graph (sec. 5)

provider_id
## 1
## 2
## 3
Data repairing (Section 5.2)
Traverse the FD pattern graph
to compute repairs

Clean data (D’)
t1: ([fd1], {“GF903”, “1407 Wescam Court”}) ▷([fd2],
{“1407 Wescam Court”, “T75”}) ▷ ([fd3], {“T75”, “212”})
## 1
Generate pattern expressions
cid
provider_
id
provider_
address
provider_
area_id
service_
area
## 1GF903
## 1407 Wescam
## Court
## T75212
## 2GF903
## 1407 Wescam
## Court
## T75212
## 3GF903
## 1407 Wescam
## Court
## T75212
## 4YT43
## 1407 Wescam
## Court
## T75212
## 5YT43
## 1407 Wescam
## Court
## T75212
6RG09160 Asher StT75212
## 2
## 0
## 2
## GF903
## YT43
## RG09
## 140 W Court
## 1407 Wescam
## Court

## 160 Asher St
## T75
## 212
## 2
## 1
## 21
## 1
## 3
## 4
t
## 1
t
## 2
t
## 3
t
## 4
t
## 5
t
## 1
t
## 2
t
## 3
t
## 4
t
## 5
Dirty data (D)
## Input
cost: 4
support: 9
provider_
address
provider_
area_id
service_
area
Update data with computed pattern expressions
t2: ([fd1], {“GF903”, “1407 Wescam Court”}) ▷([fd2],
{“1407 Wescam Court”, “T75”}) ▷ ([fd3], {“T75”, “212”})
t3: ([fd1], {“YT43”, “1407 Wescam Court”}) ▷([fd2],
{“1407 Wescam Court”, “T75”}) ▷ ([fd3], {“T75”, “212”})
cost: 2
support: 6
t
## 6
t
## 6
## (a)
## (b)
## (c)
## (f)
## (d)(e)
Figure 2:Horizonat a glance.
b
○Horizoncomputes the FD pattern graph.
c
○Performs static analysis on the FDs to devise a
traversal order of the graph in Step
b
## ○.
d
○Repairs the input tuples and presents the results to the user in
f
## ○
e
## ○
enforce simple FD rules on small datasets. Figure 1 reports the
runtime of various state-of-the-art data cleaning systems to repair
FD violations on a real-world dataset (refer to Section 6 for further
detail on baselines and setup). It is clear that current systems do
not scale well with regard to dataset size. Even for moderately sized
datasets (e.g., 1M), most of the baselines do not terminate within
24 hours on a 32GB memory machine with an 8-core CPU.
In this paper, we introduceHorizon, an end-to-end FD repair
system that efficiently cleans data using a novel cost model that
preserves the frequent patterns found in the input data.Horizon
outperforms state-of-the-art cleaning systems on both effectiveness
of FD repairs and efficiency. In the remainder of this section, we
outline the intuition behindHorizon’s repair strategy, and discuss
limitations of existing methods through a motivating example. In
the subsequent sections, we exploreHorizon’s repair model in more
detail, and how it is amenable to an efficient implementation.
Modeling Value Combinations. One way to capture value com-
binations that bind semantically-related attributes is through FDs.
When  instantiated  on  the  data,  these  FDs  form  data  patterns
that bind together semantically-related data values. For instance,
in  Figures  2a-b,  the  pattern  [provider_address=  “1407  Wescam
Court",  provider_area_id  =  “T75"]  is  a  binding  of  data  values
[provider_address= “1407 Wescam Court"] and [provider_area_id
= “T75"] through푓푑
## 2
. Consequently, every FD generates a set of
patterns. We refer to these patterns asFD patterns. We propose
to extract FD patterns from the dirty data and reason about their
quality and interactions to compute data repairs. Since correct data
is a genuine representation of reality, correct values will usually
maintain some patterns based on their distribution and relation-
ships [25,32]. Therefore, we want to pick repairs that result in pat-
terns that are well-supported in the data (e.g., [provider_address=
“1407 Wescam Court", provider_area_id = “T75"] is more frequent
than [provider_address= “140 W Court", provider_area_id = “0"].
Example 1.Table D (Figure 2a) is a data snippet based on a col-
laboration we have with an organization (Company X) that connects
customers to providers for various services.퐷has five attributes:
(1) cid: Customer identifier; (2) provider_id: Service provider identifier;
(3) provider_address: Address of the provider; (3) provider_area_id:
Identifier of a provider’s area; (4) service_area: Customer’s area
code. We use the FDs:푓푑
## 1
## :푝푟표푣푖푑푒푟_푖푑→푝푟표푣푖푑푒푟_푎푑푑푟푒푠푠
(Records with the same provider id must have the same provider
address),푓푑
## 2
:푝푟표푣푖푑푒푟_푎푑푑푟푒푠푠→푝푟표푣푖푑푒푟_푎푟푒푎_푖푑(Records
with the same provider address must have the same provider area
id) and푓푑
## 3
:푝푟표푣푖푑푒푟_푎푟푒푎_푖푑→푠푒푟푣푖푐푒_푎푟푒푎(Records with the
same provider area id must have the same service area code). In Fig-
ure 2a, the cells involved in the violation of푓푑
## 1
are highlighted.
Given a dirty table and FDs (Figure 2a),Horizoncreates a graph,
termed FD Pattern Graph (FDG) (Figure 2b), that combines all the
FD patterns in the data, and then selects the repairs with maximal
support. In Figure 2b, each edge is an FD pattern and its weight
corresponds to the number of records that support the pattern in
table퐷. Most existing repair algorithms rely on theminimalitycost
model, i.e., picking the repairs that result in the least changes to the
data. However, minimality falls short when dealing with patterns
(instead of individual cells). For instance, in Figure 2b, the pat-
tern [provider_address = “1407 Wescam Court”, provider_area_id
= “T75”] is more frequent than the pattern [provider_address =
“140 W Court”, provider_area_id = “0”]. However, the repair (or
path) that selects the frequent pattern costs more (in terms of up-
dates) than the alternative path (4>2), but has higher support
(9>6). While there is no guarantee that the path with the highest
support is always the correct one, our empirical evaluation clearly
shows that the pattern granularity offers more context for selecting
high-quality repairs than cells seen in isolation.
Repair Side Effects. When a repair algorithm is faced with con-
flicting values, oftentimes every choice will affect the underlying
patterns in the data. For instance, in Example 1, choosing “140 W
Court” over “1407 Wescam Court” (for cell푡
## 3
## [푝푟표푣푖푑푒푟_푎푑푑푟푒푠푠])
to repair the푓푑
## 1
violation will result in incorrect patterns, e.g.,
[provider_address = “140 W Court", provider_area_id = “0”].Hori-
zonconsiders how a repair choice for one FD affects the patterns
of subsequent FDs (Figure 2b).
## 2547

Typically, FD repair algorithms work in two phases: (1) Error de-
tection which detects all the violating tuple pairs, and (2) Repairing
that typically focuses on minimizing the changes to the violating
cells so as to satisfy all the FDs, which constitutes a hard optimiza-
tion problem [21].Horizondisrupts this traditional workflow by
(1) Using FDs as generative rules to produce a graph that encodes
the FD-induced data patterns and their interactions; (2) Static anal-
ysis on the FDs to dissect the interactions among them (Figure 2c);
and (3) Traversing the graph in linear time to select patterns that
are “most supported” in the data (Figure 2d).
## Representation
. To ease their readability,Horizonpresents repair
results in an intermediate representation that we refer to aspattern
expressionsthat shows the lineage of a given repair, instead of
showing isolated cell updates generated by repairs. Example pattern
expressions are given in Figure 2(e), where each output record is a
“composition” of several FD patterns. The composition operator▷
“joins” two FD patterns sharing the same attribute value.
## Contributions.
## 1.
We propose FD patterns to model value combinations and their
interactions throughFDs. We compile FD patterns into a graph data
structure (FDG) withinHorizonto clean the input data (Section 3.2).
2.We present measures forHorizonto reason about the quality of
the FD patterns in the FDG that captures the intrinsic quality of
the FD patterns and the ones they lead to (Section 3.3).
3.We transform the cleaning problem into an FD pattern mapping
problem and develop algorithms inHorizonto generate repairs in
linear time in the size of the data and FDs (Sections 4, 5).
4.We conduct a thorough experimental study to assess the perfor-
mance ofHorizonagainst a variety of state-of-the-art data repairing
algorithms (Section 6). We evaluateHorizon’s scalability using vari-
ous datasets including a real-world dataset with 64M records.
## 2  RELATED WORK
For simplicity, we classify the repairing methods into two categories:
(1)Rule-based [18, 21]: These are the most related to our work.
They produce an instance that is consistent with a set of constraints
(e.g., FDs, CFDs). In this category, we have methods that focus solely
on FDs (FD-centric), and those that address other types of rules
(e.g., CFDs, DCs), which might encompass FDs (non-FD-centric).
(2)General: These are general data cleaning methods [15,25,30]
that were not designed to address a particular type of data errors,
but strive to repair any cell that might contain an error.
Rule-based Data Cleaning.Existing rule-based data repairing
techniques focus on computing repairs that minimally change the
data instance to satisfy a set of rules, e.g., FDs [6,8,9,14,20,23],
Conditional FDs [6,12,13,19], Fixing Rules [31], Order Depen-
dencies [27], and Denial Constraints [10]). For instance,SAMP[6]
produces repairs of FDs and CFDs by sampling from the space of
possible repairs.Holisticrepairs violations of denial constraints
by leveraging the overlap between violating cells. Most of these
methods use the subset of violating cells to find repairs.
Horizonprovides a significant addition to this family of algo-
rithms from the wayHorizonmodels the data (the FD patterns) to
the way it maps patterns to each other to produce a repaired in-
stance efficiently. Furthermore, unlike existing rule-based solutions,
Horizonbenefits from evidence from all the data values in the dirty
instance, including those that are not involved in violations.
[7,9] address the problem of repairing the FDs in addition to
data. For instance,Unified[9] decides whether it is best to repair
the data, or repair the FDs by computing support measures for data
patterns. However, in addition to their inherent inefficiency, the
repairing cost model is still minimality.
General Data Cleaning.HoloClean[25] uses probabilistic infer-
ence to produce repairs based on different signals (e.g., constraint
violations). Repairs are associated with marginal probabilities that
reflect their accuracy. Another recent effort isBaran[24] that com-
bines various data correction models to clean data cells.Horizonis
different fromHoloCleanandBaranin three ways: (1) They both
have to know which cells are erroneous, and this could be hard
to get whereas퐻표푟푖푧표푛has to find out automatically which cells
might contain errors through the FDs; (2) They were both designed
for generality, i.e., to clean a large class of data errors. This gen-
erality puts them at a disadvantage compared toHorizonwhich is
tailored to deal with FD errors, allowing it to benefit from their
interactions to produce repairs. (3) They do not produce repairs
that are necessarily consistent w.r.t. a set of constraints.
SCARE[32], a probabilistic approach that relies on predicting
attribute values given the data distribution. However, the user’s
feedback is needed to assess the quality of the repairs. In addition,
SCAREis not bound by any data quality rules.KATARA[11] is a
cleaning system that employs external, curated knowledge bases
in addition to crowdsourcing to derive repairs. Both methods are
different in scope in contrast toHorizon.
## 3  COMPUTING THE FD PATTERN GRAPH
## 3.1  Background
Let푅be  a  relational  schema  of  a  data  instance퐼.  Let퐴=
## {퐴
## 1
## ,퐴
## 2
## , ...,퐴
## 푛
}be the set of attributes in푅with active domains
## 푑표푚(퐴
## 1
## ),푑표푚(퐴
## 2
## ), ...,푑표푚(퐴
## 푛
)respectively. LetΣbe the set of func-
tional dependencies (FDs) defined over푅. We assume thatΣis
minimal and in canonical form [2]. An FD푓푑
## 푖
inΣ(푖<|Σ|) has the
format푋→푌, where푋,푌∈퐴.푋and푌are referred to as the an-
tecedent and consequent attributes, respectively. Let퐿푒푓푡(푓푑
## 푖
## )and
## 푅푖푔ℎ푡(푓푑
## 푖
)be the left- and right-hand sides of푓푑
## 푖
, respectively. The
set of attributes involved in푓푑
## 푖
andΣare referred to as푎푡푡푟(푓푑
## 푖
## )
and푎푡푡푟(Σ)respectively. When푓푑
## 푖
is projected on a tuple푡, we
refer to푡[푋]and푡[푌]as퐿퐻푆and푅퐻푆values of푓푑
## 푖
on푡. An in-
stance퐼=
## {
## 푡
## 1
## ,푡
## 2
## , ...,푡
## 푛
## }
of푅satisfiesΣ, denoted by퐼|=Σ, if퐼has
no violations (i.e., every pair of tuples with the same퐿퐻푆value
must have the same푅퐻푆value) of any of the FDs inΣ. A cell푡[퐴]
denotes the value of attribute퐴in tuple푡. Every tuple has a unique
identifier. The set of tuple identifiers in퐼is denoted푇퐼퐷(퐼).
Definition 1.Repair Instance [23] Given an instance퐼of schema
푅violating FDsΣ, an instance퐼
## ′
is a repair of퐼iff퐼
## ′
## |= Σand
## 푇퐼퐷(퐼)=푇퐼퐷(퐼
## ′
## )
According to Definition 1, a repair is achievable only by modi-
fying attribute values of tuples. Insertion or deletion of tuples or
attributes are not allowed. Unlike [23], our space of repairs only
contains constants from the active domain.
3.2  Encoding FD Patterns
We encode the FD patterns by projecting the FD graph on the
instance.  Refer  to  Figure  2b  for  illustration.  Every  FD  pattern
## 2548

## (푋
## 1
## ,푋
## 2
## , ...푋
## 푛
## →푌,[푥
## 1
## ,푥
## 2
## , ...,푥
## 푛
,푦])(푛≤ |퐼|) is encoded with a
directed hyperedge({푥
## 1
## ,푥
## 2
## , ...,푥
## 푛
},{푦}). We refer to푥
## 1
## ,푥
## 2
## , ...,푥
## 푛
as
the퐿퐻푆nodes and푦as the푅퐻푆node.
FD Pattern Graph (FDG):The FDG of instance퐼is a directed
hypergraph [5]퐺(푉,퐸), where: (1) Each node푣∈푉has two at-
tributes푣.푎푡푡푟푖푏푢푡푒and푣.푣푎푙encoding an attribute푎∈퐴and
a data value푑∈푑표푚(푎), respectively; (2) A directed hyperedge
푒(푊,푍)∈퐸that (a) connects nodes in푊(tail) to a node in푍
(head) such that|푍|= 1 and|푊|≥1; and (b) encodes an FD pattern
## 푝(푋
## 1
## ,푋
## 2
## , ...,푋
## 푛
## →푌,[푥
## 1
## ,푥
## 2
## , ...,푥
## 푖
,푦])∈퐼(푛≤ |퐼|) such that there
is a node푤∈푊where푤.푎푡푡푟푖푏푢푡푒=푋
## 푖
and푤.푣푎푙=푥
## 푖
for all
푖≤ |퐼|, and푍.푎푡푡푟푖푏푢푡푒=푌,푍.푣푎푙=푦.
For example, the graph in Figure 2b is the FD pattern graph for
table퐷(Figure 2a). Each edge represents an FD pattern. In the
sequel, since they represent the same thing, we employ the terms
“FDG edge” and “FD pattern” interchangeably. Additionally, to ease
the readability of the graph figures, we label the nodes with their
values and omit the attribute names.
## 3.3  Pattern Quality
Our target is to select “good” FD patterns in the FD pattern graph to
compute instance repairs. Therefore, it is crucial to characterize the
quality of FD patterns in the FD pattern graph. This step is required
by the repair algorithm (Section 5.2) to reason about the quality of
various candidate FD patterns. We now present a general model
to characterize the quality of FD patterns that also captures their
interactions. By looking at an FD pattern푃: (푋→푌,[푥,푦])as an
association rule [3] (푃[푥]→푃[푦]), we can compute its푆푢푝푝표푟푡
(푆푢푝) as the number of tuples with푋=푥and푌=푦in퐼over the
number of tuples in퐼.
## 푆푢푝(푃) =
## |푃|
## |(푋→푌,∗,∗)|
## (1)
In the above equations, * denotes “any value”.
As illustrated in Example 1, greedily selecting FD patterns based
on their frequencies is not a good strategy for selecting the best FD
patterns. That is, in Figure 2b, the edges [“YT43”, “1407 Wescam
Court”] and [“GF903”, “140 W Court”] have the same weight. There-
fore, it would be better if the score of an FD pattern not only includes
its own support, but also the support of the FD patterns it can lead
to. Thus, we extend푆푢푝in Equations 1 to capture the quality of an
FD pattern푃by the set of FD patterns it can lead to (denoted푃
## →
## )
as follows:
## 푄푢푎푙푖푡푦(푃) =
## 푆푢푝(푃) +
## ∑︁
## 푄∈푃
## →
## 푆푢푝(푄)
## |푃
## →
## |+1
## (2)
The enumerator of푄푢푎푙푖푡푦(푃)(Equation 2) is the sum of: (1) the
푆푢푝푝표푟푡of푃, and (2) the푆푢푝푝표푟푡of all the FD patterns that can
be reached from푃. We normalize the quality of a pattern using the
average over the number of edges in|푃
## →
## |.
Horizonperforms a Depth-First Search (DFS) traversal over the
FDG and computes the quality of each visited edge using Equation 2.
To guarantee termination, back-edges (corresponding to cyclic FDs)
are processed when the DFS traversal is complete. Specifically,
Horizonperforms the following steps: (1) Build a DFS tree from
the input root vertex푣; (2) For every edge푒= (푣,푤), if푒is a back-
edge add it to a set퐵푎푐푘퐸푑푔푒푠. If not, compute the edge quality;
(3) Assign the quality of the root vertex (The quality of a vertex푣
is the average quality of all the edges that can be reached from푣).
After the DFS step is completed, all back-edges are processed. The
quality of a back-edge푒= (푣,푤)is the quality assigned to vertex
푤in the DFS step. Since it amounts to a DFS, the time and space
complexities of computing and propagating scores in an FD pattern
graph퐹퐷퐺(푉,퐸)are both푂(|푉|+|퐸|).
## 4  RULES COMPILATION
4.1  Interactions among FD Patterns
Figure 3a enumerates four cases in which FD patterns interact with
each other. FD patterns푃
## 푖
## : (푓푑
## 푖
## ,푉
## 푖
## )and푃
## 푗
## : (푓푑
## 푗
## ,푉
## 푗
## )(푓푑
## 푖
## ,푓푑
## 푗
## ∈Σ
and푉
## 푖
## ,푉
## 푗
are values assigned to푎푡푡푟(푓푑
## 푖
## )and푎푡푡푟(푓푑
## 푗
## )respectively
with푖̸=푗) interact with each other iff: (1)푓푑
## 푖
and푓푑
## 푗
share at
least one attribute, and (2) the value of the shared attribute(s) is the
same in푉
## 푖
and푉
## 푗
. Note that different cases of interactions have
different semantics. Consider a dirty tuple푡containing two FD
patterns푃
## 푖
and푃
## 푗
corresponding to two different FDs푓푑
## 푖
and푓푑
## 푗
## .
Without loss of generality, we discuss interaction cases with FDs
that have one attribute in their antecedent.푃
## 푖
and푃
## 푗
can exhibit
the following four cases of interaction depending on the FDs they
embed (Figure 3a):
## Case 1 (푓푑
## 푖
## =퐴→퐵,푓푑
## 푗
## =퐴→퐶):푡[퐴] =푎
## 1
can be mapped
to any RHS value in퐵and퐶, i.e., the choice of values of퐵is
independent of the choice of the value of퐶. In other words, choosing
the RHS of푎
## 1
to satisfy퐴→퐵does not affect the choice of the
RHS of푎
## 1
to satisfy퐴→퐶.
## Case 2 (푓푑
## 푖
## =퐴→퐶,푓푑
## 푗
## =퐵→퐶):푡[퐴] =푎
## 1
and푡[퐵] =푏
## 1
must
be mapped to the same RHS value퐶. In other words, Patterns푃
## 푖
and푃
## 푗
have to share the퐶value. Thus, the choice of the퐶value
for퐴affects the choice of the퐶value for퐵, and vice-versa.
## Case 3 (푓푑
## 푖
## =퐴→퐵,푓푑
## 푗
=퐵→퐶): In this case, the consequent
of푃
## 푖
is the antecedent of푃
## 푗
. In this case, the choice of the value of
퐵affects the퐶value. That is, choosing a value퐵=푏
## 푥
in푃
## 푖
would
make푏
## 푥
the antecedent of푃
## 푗
## .
## Case 4 (푓푑
## 푖
## =퐴→퐵,푓푑
## 푗
=퐵→퐴): This is the case of circular
FDs; the choice of the value of퐴affects the choice of the value of
퐵and vice-versa.
In the above cases, depending on the interaction case of the FDs,
selecting an FD pattern for one FD in a tuple푡may affect the choice
of the FD patterns for the subsequent FDs that interact with it. Next,
we formalize this observation.
4.2  Determining Bound and Free Attributes
FDs impose a “many-to-one" relationship between LHS and RHS
values. That is, for the instance to be consistent, a LHS value is
mapped to a single RHS value. An attribute퐴that does not appear
as a RHS of an FD is said to be aboundattribute. Bound attributes
have two properties: (1) They appear as part of a LHS inΣand are
thus used todeterminethe value of RHS attributes, and (2) Since
they do not appear as RHS attributes inΣ, we cannot use other
attributes to determine their values (because of the many-to-one
relationship, we can only determine attribute values from LHS to
RHS and not the other way around). If an attribute is notbound,
then, it is afreeattribute, i.e., its values are determined from other
(LHS) attributes. Obviously, an attribute cannot be푏표푢푛푑and푓푟푒푒
## 2549

a
## 1
b
x
## A
## B
c
y
## C
a
## 1
c
x
## A
## C
b
## 1
## B
a
## 1
b
x
## A
## B
c
y
## C
a
## 1
b
x
## A
## B
## Case 1
## (A → B; A → C)
For a given a
## 1
, the
choice of B and C
values is
independent

## Case 2
## (A → C; B → C)
For a given a
## 1
and
b
## 1
, we must select a
single C value.

## Case 4
## (A → B; B → A)
For a given a
## 1
(or b
## 1
), we
must select a single B
value (or A value).

## Case 3
## (A → B; B → C)
For a given a
## 1
the choice
of B affects the choice of C

## P
## 1
## P
## 2
## P
## 1
## P
## 2
## P
## 1
## P
## 2
## P
## 1
## P
## 2
c
## 2
## 2

c
## 0
## 0
- Build FD graph
- Build SCC graph of FD graph and compute
topological sorting on its components
- Call OrderFDs() and compute a traversal order
for each FD
provider_id
provider_
address
provider_
area_id
service_
area
fd
## 1
fd
## 2
fd
## 3
fd
## 4
provider_address
provider_id →  provider_address0
provider_address →  provider_area_id
provider_area_id →  service_area
service_area → provider_area_id
## 1
## 2
## 3
## FD
## Order
## (a)
## (b)
provider_id
provider_
area_id
service
## _area
c
## 1
## 1

Figure 3: FD Patterns interaction cases
at the same time. Therefore, allfreeattributes must appear as RHS
attributes inΣ(we discuss cyclic FDs next).
Proposition 1.For every푓푟푒푒attribute퐴inΣ, there must exist
at least an attribute퐵such that: (1) There is an FD푓푑
## 푖
## (퐵→퐴)∈Σ;
(2) If there is an FD푓푑
## 푗
(퐴→퐵)∈Σ, then, there must exist at least
an FD푓푑
## 푘
∈Σwhere푓푑
## 푘
(퐶→퐴) or푓푑
## 푘
## (퐶→퐵). If푓푑
## 푘
̸∈Σ, we
designate either퐴or퐵to be a푏표푢푛푑attribute.
Proposition 1 states that every푅퐻푆attribute (free attribute) has to
have at least one set of퐿퐻푆attributes that determines it inΣ. This
is trivial when there are no cyclic FDs. However, ifΣhas cyclic FDs,
some attributes could be푓푟푒푒but would not have an퐿퐻푆attribute
that determines them outside the cycle. For instance, consider the
FDs in Figure 4a where푝푟표푣푖푑푒푟_푎푟푒푎_푖푑and푠푒푟푣푖푐푒_푎푟푒푎arefree
attributes because they both appear as푅퐻푆inΣ.
## 5  TRAVERSING THE FD PATTERN GRAPH
FDG node values from bound attributes are assigned from the in-
put tuples. For example, consider tableDand its FDs in Figure 4a
(shaded cells correspond to fixed values and cell values “*” corre-
spond to cells that we can change) and its corresponding FD pattern
graph in Figure 4b (edge weights are quality scores as presented
in Section 3.3). The set of푏표푢푛푑attributes contains푝푟표푣푖푑푒푟_푖푑
while all the other attributes involved in the FDs are free.
Proposition 2.For an assignment훽of bound attribute nodes
퐴in the퐹퐷퐺(푉,퐸), there exists a subgraph퐺(퐾,퐵)such that: (1)
퐾⊂푉and퐵⊂퐸and퐴⊂퐾; (2)∀푓푑(푋→푌)∈Σ :∃푒(푈,푊)∈퐵:
## 푈.푎푡푡푟푖푏푢푡푒=푋∧푊 .푎푡푡푟푖푏푢푡푒=푌.
Proposition 2 states that assigning values to the푏표푢푛푑attribute
nodes in the FD pattern graph produces a subgraph (referred to as
the chase graph) that covers all the FDs inΣ. In other words, the
set of bound attribute values is all we need to determine the value
of all the other attributes inΣ. Figure 4b illustrates the chase graph
generated with푝푟표푣푖푑푒푟_푖푑as the bound attribute. For example,
given Tuple푡
## 1
in퐷(Figure 4a), the assignment of the bound at-
tribute is훽={푡1[푝푟표푣푖푑푒푟_푖푑] = “퐺퐹903”}, all the other attributes
inΣcan be modified. Then, we start the chase to get the FD pat-
terns of all the FDs from the FD pattern graph (highlighted path in
Figure 4b). Then, the resulting chase graph is translated to an FD
pattern expression and used to repair tuple푡
## 1
(Figure 4c).
cidprovider_id
provider_
address
provider_
area_id
service_
area
## 1GF903***
## 2GF903***
## 3GF903***
## 4YT43
## 1407 Wescam
## Court
## T75212
## 5YT43
## 1407 Wescam
## Court
## T75212
6RG09160 Asher StT75212
Functional dependencies (횺)
FD pattern graph
Edge weights are edge quality scores
The highlighted path is the chase graph to repair t
## 1
Clean data (D’)
t1: t1: ([fd1], {“GF903”, “1407 Wescam
## Court”}) ▷([fd2], {“1407 Wescam Court”,
“T75”}) ▷ ([fd3], {“T75”, “212”})  ▷ ([fd4],
## {“212”, “T75”})
cid
provider_
id
provider_
address
provider_
area_id
service_
area
## 1GF903
## 1407 Wescam
## Court
## T75212
## 2GF903
## 1407 Wescam
## Court
## T75212
## 3GF903
## 1407 Wescam
## Court
## T75212
t
## 1
t
## 2
t
## 3
t
## 4
t
## 5
t
## 1
t
## 2
t
## 3
Dirty data (D)
## Input
Update data with computed pattern expressions
t
## 6
## (a)
## (b)
## GF903
## YT43
## RG09
## 140 W Court
## 1407 Wescam
## Court

## 160 Asher St
## T75
## 212
## 0.33
## 0.44

## 0.5
## 0.32
## 0.41

## 0.58
## 0.33
## 0
## 0.33

## 0.49
## 0.44

## 0.66
## (c)
fd
## 1
: provider_id → provider_address
fd
## 2
: provider_address → provider_area_id
fd
## 3
: provider_area_id → service_area
fd
## 4
: service_area → provider_area_id

Figure 4: Example of repairing a tuple
5.1  Traversal order
Following the boundedness of attributes, we devise a traversal
order of the FDG. Since the FDs can have cycles, we cannot di-
rectly apply standard topological ordering of the nodes in the FD
graph. Instead, we first apply topological sorting on the Strongly
Connected Component Graph (SCCG) induced by the FD graph
(SCCG is guaranteed to be a DAG). We obtain the SCCG using the
푇푎푟푗푎푛algorithm [28] that runs in푂(|퐴|+|퐸|), where퐴and퐸are
the vertices and edges in the FD graph, respectively.
Figure 3b illustrates how we go from the FD graph (top canvas)
to the SCCG (middle canvas), and finally to ordering the FDs. Note
how each SCC푐
## 푖
has an order표assigned to it (denoted푐
## 표
## 푖
## )).
5.2  Pattern-Preserving Repairs
We present a linear-time repair algorithm that computes a repair
instance in the form of pattern expressions. Notice that a pattern
expression that covers all the FDs inΣcorresponds to achase graph
in the FDG. Our final goal is to choose chase graphs that have high
edge weights without resorting to an exponential solution.
Algorithm 1 takes as input a dirty table퐷and the set of FDsΣ,
and produces pattern expressions that correspond to clean tuples.
Repair tables (푅푡푎푏푙푒in Algorithm 1) collect all the퐿퐻푆to푅퐻푆
mappings done so far and are used to update the input tuples
accordingly. First, we build the FD pattern graph and compute
its edge weights (Lines 1-2), and compute the order of FDs (Lines
3-5). We process the input data one tuple at a time (line 7), and
## 2550

Algorithm 1:GeneratePatternPreservingRepairs(Σ,퐷)
output:For every tuple in퐷, return a pattern expression
1FDG←BuildFDPatternGraph(퐷,Σ)
2FDG←ComputePatternsQuality(IG)
3SCCG←BuildSCCGraph(Σ)
4OC←TopologicalSorting(SCCG)
5Ordered_FDs←OrderFDs(Σ,푂퐶)
## 6pattern_expressions← ∅
7forallTuple t∈퐷do
8fori←0 to|Ordered_FDs|do
9forallFD푓∈푂푟푑푒푟푒푑_퐹퐷푠[푖]do
10Lval←t[f.LHS]
11ifRtable(f).contains(Lval)then
12FDPattern p←New FDPattern(f, Lval→
Rtable(f ).get(Lval))
## 13푃
## 푒푥푝
## (푡)←푃
## 푒푥푝
## (푡)▷p
14else iff.RHS∈푃
## 푒푥푝
## (푡)then
15FDPattern p←New FDPattern(f, Lval→
GetAttributeValue(푃
## 푒푥푝
(푡), f.RHS))
## 16푃
## 푒푥푝
## (푡)←푃
## 푒푥푝
## (푡)▷p
17Rtable(f ).Add(Lval, GetAttributeValue(푃
## 푒푥푝
(푡), f.RHS))
## 18else
19FDPattern p←Edge_Selection(FDG)
## 20푃
## 푒푥푝
## (푡)←푃
## 푒푥푝
## (푡)▷p
21Rtable(f ).Add(Lval, p.RHS)
22pattern_expressions = pattern_expressions∪푃
## 푒푥푝
## (푡)
create a pattern expression푃
## 푒푥푝
(푡)for each Tuple푡by building
the chase graph from the FDG (lines 18-21). Then, the (LHS, RHS)
mappings are written into the repair tables of each corresponding
FD (lines 17 and 21). We handle the cases of a LHS that is (1) already
mapped in a previous iteration (lines 11- 13); (2) already mapped
to a푅퐻푆from another FD (lines 15- 17); or (3) not mapped yet, in
which case we add a new pattern from the퐹퐷퐺(lines 19- 21).
## 6  EXPERIMENTAL STUDY
We present an experimental evaluation to answer the following
questions: (1) How doesHorizonperform under different error types
and rates? (2) How doesHorizoncompare to state-of-the-art rule-
based and non-rule-based cleaning techniques in terms of repair
quality and runtime? (3) How scalable isHorizon?
## 6.1  Setup
Datasets.We use the following four datasets: (i)DataXis a pri-
vate dataset from an active collaboration withCompany Xto clean
their data.DataXintegrates data from over 1,600 data sources and
contains information about customers, their personal information
and service providers that serve those customers. It contains 64M
records, 43 attributes, over 2B and 750 million cells and 10 FDs. We
have a sample of 470 correct cells that we use as the ground truth.
(ii)Parkingis a real-world dataset of parking ticket information for
New York City [1] with 9M records and 9 FDs. We used a labeled
random sample of 100 cells as the ground truth. Because the com-
peting baselines we evaluate cannot handle larger datasets, we used
a 100K and 20k records forParkingandDataXrespectively in the
effectiveness experiments and the whole 9M and 64M records (for
ParkingandDataXrespectively) records for the runtime experi-
ments. (iii)Hospitalis a real-world dataset on health-care providers
and hospitals [10]. It contains 100K records and 13 FDs. (iv)Taxis a
Table 1:Data and FD properties of the datasets
DatasetTaxHospitalParkingDataX
## Avg. Redundancy8915.896274.03540.464431.59
Atts w. AvgRed.≤53020
## Avg.|푣푎푙|3.7918.874.625.04
Attribute overlap0.770.710.850.58
synthetic dataset [17] with 6 FDs that contains records on tax infor-
mation for individuals, e.g.,first name, last name, andwhether the
person has a child. For measuring effectiveness, we use 100K records
(Tax) while we generate 5M records for the scalability experiment
(Tax_Extended).
Datasets properties.Table 1 reports key dataset and FD proper-
ties which may affect the performance ofHorizon. (1) The average
redundancy is the average frequency of each attribute value. The
number of attributes whose average redundancy is less or equal
than 5 is reported in퐴푡푡푠 푤.퐴푣푔푅푒푑≤5. (2) Attribute overlap
measures the overlap of attributes across the FDs.
## Errors.
We  divide  our  experimental  study  into  two  parts:
(1) Controlled errors (CE): We conduct a thorough experimental
study to benchmarkHorizonand its competing baselines under
various error types and rates. Similar to existing data cleaning liter-
ature, e.g., [10,18,22] to cite a few, we use the state-of-the-art data
cleaning benchmarking system BART [4] to control the injected
error rate and type of errors. BART introduces synthetic errors to
theTaxandHospitaldatasets that would trigger violations of their
corresponding FDs. More specifically, we generate errors for all
their FDs with varying noise levels and using different data sizes.
We introduce two types of errors to theHospitalandTaxdatasets:
•Error-1 (E1):BART injects the input datasets with FD-detectable
errors that include values from the active domain (e.g., replace
“NY” with “CA”) making it harder for the repair algorithms to
find the correct repair if the candidate repair values are all well
supported in the data.
•Error-2 (E2):In order to experiment with all kinds of errors,
BART allows generating errors that may or may not be FD-
detectable. These errors include outliers.
(2) Uncontrolled errors (UE)
: In this part, we do not inject errors
and instead correct errors that are naturally occurring in the data.
We evaluateParkingandDataXfor these experiments.
Baselines.We compare the following repair algorithms toHorizon:
•Holistic[10],SAMP[6],Unified[9],HoloClean[25] andBaran[24]
have been introduced in Section 2. ForUnified, since we assume
the FDs are correct inHorizon, we evaluated the data repairing
part ofUnifiedonly.
•Min[8].Minfirst assigns groups of cells that need to have the
same value to different equivalence classes, then, a value is chosen
for each equivalence class to repair the FD violations.
We picked different flavors of repair algorithms to show how
Horizoncompares to (1) a variety of FD-centric baselines (SAMP,
Min, andUnified); (2) one non-FD-centric baseline (Holistic) and
(3) general repair techniques (HoloCleanandBaran).
Metrics.(1) Precision (P): The number of correctly repaired cells
over the total number of repaired cells; (2) Recall (R): The number
of correctly repaired cells over the total number of dirty cells; and
(3) F1 score computed as2(푃∗푅)/(푃+푅). Since푆퐴푀푃may generate
different results in each run, we took the average of five runs to
compute these metrics.
## 2551

Table 2:Rule-based baselines effectiveness results (CE on the left, and UE on the right). E = Error type, P = Precision, R = Recall, F1 = F1 score
AlgorithmE
TaxHospital
## PRF1PRF1
HorizonE10.810.740.760.930.770.84
## E20.80.270.380.880.610.71
## Holistic
## E10.160.870.250.040.280.06
## E20.220.190.190.480.040.03
## SAMP
## E10.080.340.090.200.290.20
## E20.120.0800.240.430.29
## Unified
## E10.120.010.010.820.660.73
## E21.0000.610.70.65
## Min
## E10.320.70.430.420.60.49
## E20.290.260.270.990.760.85
## Algorithm
ParkingDataX
## PRF1PRF1
## Horizon
## 0.980.560.70.930.930.93
## Holistic0.430.120.181.00.080.14
## SAMP0.140.0200.20.320.24
## Unified0.420.10.160.710.060.11
## Min0.10.040.050.950.660.77
Table 3:Non-rule-based baselines results (CE on the left, and UE on the right). E = Error type, P = Precision, R = Recall, F1 = F1 score.
AlgorithmE
TaxHospital
PRF1TimePRF1Time
HorizonE10.950.750.830.5 sec0.930.79  0.85   0.8 sec
## E2
0.850.050.090.63 sec0.980.73  0.83  0.57 sec
HoloCleanE10.850.010.0113 min1.00.090.1613 min
## E20.91
0.010.018 min1.00.610.7514 min
BaranE10.97  0.94  0.962 min1.00.140.242 min
## E2
0.720.67  0.720 min0.540.440.495.2 min
## Algorithm
ParkingDataX
PRF1TimePRF1Time
Horizon0.89   0.61   0.72    1 sec0.93   0.93   0.93    1 sec
HoloClean0.70.10.1718 min0.910.720.833 min
Baran0.140.020.011 sec1.00.20.3344 sec
Table 4:Interaction cases (IC) vs. precision (P), recall (R), F1 and
runtime (T) in sec. We use a bit array to indicate which IC is present
in the input FDs (e.g., 0101 indicates FDs involved in IC2 and IC4).
## Tax
ICs00110101011001111001101010111100110111101111
## P0.810.290.950.950.810.800.810.810.810.810.81
## R0.720.010.660.660.710.710.710.720.720.710.71
## F10.750.010.770.770.750.740.750.750.750.750.75
## T3.682.343.425.325.096.008.045.136.617.709.71
## Hospital
ICs00110101011001111001101010111100110111101111
## P0.930.930.930.930.930.930.930.930.930.930.93
## R0.810.750.750.780.780.810.800.750.760.780.78
## F10.860.820.820.840.840.860.850.820.820.840.84
## T6.017.824.909.098.875.999.527.8112.018.7513.03
Implementation and Hardware Platform.Horizonis  imple-
mented in Java. Evaluation was done on a Linux machine with
8 Intel Xeon E5450 3.0GHz cores and 32GB main memory.
## 6.2  Effectiveness Results
In Table 2, we report effectiveness results for CE (left) and UE (right).
In this section, we focus on rule-based baselines while we present
non-rule-based baselines results in Section 6.5.
Table 2 shows thatHorizonoutperforms (F1 score) all other
baselines on all datasets with one exception where it is slightly
outperformed byMinonHospitalwith E2 errors. It also outper-
forms these baselines on Precision and Recall values with very few
exceptions. As expected, E1 errors are more amenable to repairs
than E2 errors. This is because E2 errors are random and are not
necessarily FD-detectable, this is why the F1 scores for E2 errors is
generally low.Horizonperforms well on E1 errors as they usually
belong to FD patterns that are not frequent in the data, making
alternative “frequent” patterns more likely to be correct. We also
note that the repair quality ofHorizonis more or less consistent
across all datasets and characteristics (Table 1).
As for the competing baselines, ForHospitalE2,Minhas the
highest F1; due to the high redundancy in the data,Minwas able
to find the repairs even with the added noise. However, it is worse
thanHorizonon all other datasets in addition to a high runtime.
Holisticcan reach a high precision (DataXandParking), but misses
a lot of repairs (hence the low recall).Holistic,SAMP,Minperform
poorly because (1) they only focus on minimal changes to repair the
data, which in most cases does not cover all the space of repairs; and
(2) when they are undecided on a repair, they introduce special vari-
ables (outside the domain) to fix a rule violation.Unifiedperforms
poorly onTaxbecause: (1) The order of FDs inUnifiedwas causing
an incorrect fix to be performed for earlier FDs which limits the
repair choices in the subsequent FDs. (2) We noticed thatUnified
starts with FDs that have columns with lower redundancies. From
Table 1, we can see thatTaxhas the highest number of attributes
with an average redundancy that is less than 5. These attributes
appear in the FDs ofTaxmaking it hard to select the correct fix for
conflicting values in those columns, and making the wrong choices
for FDs with those columns creates bad repairs in other FDs.
Repair quality vs. error rate.Figures 5a-b report the F1 score
of repairs w.r.t. different data error rates.Horizonoutperforms the
other systems, especially as the error rate goes up. This is because
adding more errors makes it harder for minimality-based algorithms
to identify correct cell values, whereasHorizonselects values that
lead to frequent FD patterns, and hence, a better repair quality.
## Takeaways.
## 1
○Using FD patterns to repair an instance leads to
high-quality FD repairs.
## 2
## ○
Minimality does not produce high-
quality repairs.
## 3
## ○
BecauseHorizoncaptures patterns across several
attributes, the lack of redundancy on individual attributes does not
significantly affect its performance.
6.3  Repair quality vs. interaction case
In this section, we examine the effect of the different pattern Inter-
action Cases (ICs) in the input FDs on repair quality and runtime.
As discussed in Section 4,Horizonemploys four pattern interaction
cases. Table 4 reports all possible combinations among the four
ICs. We have a total of 11 configurations (we exclude the case with
0 FDs and only one IC). We use a bit array notation to indicate
which IC is present in the input FDs. For example 0101 indicates
## 2552

## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## 51015202530
## F1
## Error %
## Horizon
## HOLISTIC
## SAMP
## Unified
## Min
(a) % Errors vs. F1. (Tax)
## 0
## 0.2
## 0.4
## 0.6
## 0.8
## 1
## 51015202530
## F1
## Error %
## Horizon
## HOLISTIC
## SAMP
## Unified
## Min
(b) % Errors vs. F1 (Hospital)
## 100
## 1000
## 10000
## 100000
## 1×10
## 6
## 1×10
## 7
## 1×10
## 8
## 20k40k60k80k100k
Repair time (msec)
## #tuples
## Horizon
## HOLISTIC
## SAMP
## Unified
## Min
(c) Repair time (Tax)
## 100
## 1000
## 10000
## 100000
## 1×10
## 6
## 1×10
## 7
## 1×10
## 8
## 20k40k60k80k100k
Repair time (msec)
## #tuples
## Horizon
## HOLISTIC
## SAMP
## Unified
## Min
(d) Repair time (Hospital)
## 10
## 100
## 1000
## 10000
## 100000
## 1M2M3M4M5M
Repair time (sec)
## #tuples
## Horizon
## HOLISTIC
## SAMP
## Unified
(e) Repair time (Tax_Extended)
## 0
## 200
## 400
## 600
## 800
## 1000
## 1200
## 1400
## 1600
## 1800
## 1M2M3M4M5M6M7M8M9M
Repair time (sec)
## #tuples
## Horizon
## SAMP
## Unified
(f) Repair time (Parking)
## 5
## 10
## 15
## 20
## 25
## 30
## 35
## 40
## 45
## 50
## 55
## 8M16M24M32M40M48M56M64M
Repair time (min)
## #tuples
(g) Repair time (DataX)
Figure 5: Effectiveness and Runtime results
FDs participating in IC2 and IC4. As expected, the more interaction
cases we have in the input FDs, the higher the repair time. We
notice that IC4 (the cyclic FDs case) introduces the most overhead.
With few ICs, the quality of repairs suffers (e.g., Tax 0101);Horizon
is unable to benefit from the interactions among the FDs or the low
data redundancy inTax. The ICs that improve repair quality are
IC3 and IC1. This is expected as IC3 forms longer chains among
the FD patterns enabling the propagation of quality scores and IC1
allows choosing the푅퐻푆with the highest support.
## 6.4  Runtime Results
We report the runtime results in Figures 5c-g for all the datasets.
Horizonsignificantly outperforms all the competing baselines by
at least 3 orders of magnitude. All the competing baselines strive
to generate minimal repairs, which boils down to solving an op-
timization problem to detect and then resolve the violating cells.
All the algorithms were given a 24-hour deadline to finish running
for each data size increment. In many cases, some of the compet-
ing baselines could not terminate (missing points in Figure 5e-g).
Overall, it tookHorizonabout 75 seconds to clean the 5 million
records inTax_Extended. ForDataX,퐻표푙푖푠푡푖푐and푆퐴푀푃did not fin-
ish running even with a 1M-record partition. WithParking,푆퐴푀푃
and푈푛푖푓푖푒푑could not finish for over 1M records whileHolistic
could not even handle 1M records. It took a total of around 300
seconds to clean the 9 million records inParking(Figure 5f). In
Figure 5g we report the runtime ofHorizonusing 8M increments of
DataX. It took 53 minutes to clean the 64M records while none of
the competing baselines were able to terminate even the smallest
increment (8M) within 24 hours. The runtime ofUnifiedis affected
by the value length and average redundancy. For example,Unified
takes the longest onTaxwhich happens to have the highest number
of attributes with low redundancy (Table 1) which in turn increases
the set of unique values, and hence repair time. Furthermore, even
with the high redundancy ofHospital,Unified’s runtime is close to
the one inTaxbecauseHospitalhas a high average value length.
Overall,Unified’s runtime is unpredictable; it took 27 mins to repair
Parking(1M) while it did not finish within 24 hours for DataX (1M).
This is becauseDataXhas a (1) slightly higher avg.|푣푎푙|and (2) a
high set of candidate repairs, which leads to computing string simi-
larity across a larger number of value pairs. In general, the runtime
ofUnifiedis relatively high compared toHorizon.
## Takeaways.
## 1
○Thanks to its FDG traversal strategy,Horizoncan
scale to millions of records linearly.
## 2
○Data redundancy and value
length directly affect the performance of rule-based baselines.
6.5  Comparison to non-rule-based baselines
Table 3 summarizes effectiveness and runtime results whenHorizon
is compared toHoloCleanandBaran. In order forHoloCleanand
Baranto terminate within 24 hours, we had to evaluate them on
smaller sizes of the datasets: Hospital (20k), Tax(10k), Parking(20k)
and DataX(20k). We note the following: (1)HoloCleanandBaran
require a specification of the cells that have errors. If we consider
all the cells involved in FD violations as potentially erroneous cells,
HoloCleanandBaranperform poorly on E1 errors whileBaranper-
forms better with E2 errors inTax. (2)HoloCleanperforms well on
DataX, which has a low redundancy, suggesting thatHoloCleancan
generalize well even with a low redundancy. (3) Runtime ofHolo-
Cleanis unpredictable. It took 13 min on 20k records of퐻표푠푝푖푡푎푙,
while it took 33 min onDataX.
## Takeaways.
## 1
○Horizon’s focus on FD errors allows it to generate
higher-quality FD repairs than cleaning systems that target gener-
ality and may miss several errors that may appear as FD violations.
## 2
○The complexity of general cleaning systems makes them ineffi-
cient for iterative cleaning scenarios.
## 7  CONCLUSIONS
In this paper, we presented a novel technique that is a radical
departure from existing repair approaches both in accuracy and
scalability. Guided by the FDs,Horizongenerates a set of modi-
fications that exploit inherent FD-induced patterns found in the
data to produce a repair instance. Moreover, we leverage the FD
interactions to produce the repair instance in linear time.
## 2553

## REFERENCES
[1]  New York City Open Data. https://opendata.cityofnewyork.us.
## [2]
Serge Abiteboul, Richard Hull, and Victor Vianu (Eds.). 1995.Foundations of
Databases: The Logical Level(1st ed.). Addison-Wesley Longman Publishing Co.,
Inc., Boston, MA, USA.
[3]Rakesh Agrawal, Tomasz Imieliński, and Arun Swami. 1993. Mining Association
Rules Between Sets of Items in Large Databases(SIGMOD ’93).
[4]Patricia C. Arocena, Boris Glavic, Giansalvatore Mecca, Renée J. Miller, Paolo
Papotti, and Donatello Santoro. 2015. Messing Up with BART: Error Generation
for Evaluating Data-cleaning Algorithms.Proc. VLDB Endow.9, 2 (Oct. 2015),
36–47.   https://doi.org/10.14778/2850578.2850579
## [5]
Giorgio Ausiello and Luigi Laura. 2017.   Directed hypergraphs: Introduction
and fundamental algorithms—A survey.Theoretical Computer Science658 (2017),
293–306.   https://doi.org/10.1016/j.tcs.2016.03.016 Horn formulas, directed hy-
pergraphs, lattices and closure systems: related formalism and application.
[6]George Beskales, Ihab F. Ilyas, and Lukasz Golab. 2010. Sampling the Repairs of
Functional Dependency Violations under Hard Constraints.Proc. VLDB Endow.
3, 1 (2010), 197–207.  https://doi.org/10.14778/1920841.1920870
[7]George Beskales, Ihab F. Ilyas, Lukasz Golab, and Artur Galiullin. 2013. On the
relative trust between inconsistent data and inaccurate constraints. In29th IEEE
International Conference on Data Engineering, ICDE 2013, Brisbane, Australia, April
8-12, 2013, Christian S. Jensen, Christopher M. Jermaine, and Xiaofang Zhou (Eds.).
IEEE Computer Society, 541–552.  https://doi.org/10.1109/ICDE.2013.6544854
[8]Philip Bohannon, Wenfei Fan, Michael Flaster, and Rajeev Rastogi. 2005.   A
Cost-based Model and Effective Heuristic for Repairing Constraints by Value
Modification. InProceedings of the 2005 ACM SIGMOD International Conference
on Management of Data(Baltimore, Maryland)(SIGMOD ’05). 143–154.   https:
## //doi.org/10.1145/1066157.1066175
[9]Fei Chiang and Renée J. Miller. 2011.  A unified model for data and constraint
repair.2011 IEEE 27th International Conference on Data Engineering(2011), 446–
## 457.
## [10]
Xu Chu, Ihab F. Ilyas, and Paolo Papotti. 2013.  Holistic data cleaning: Putting
violations into context. In29th IEEE International Conference on Data Engineering,
ICDE 2013, Brisbane, Australia, April 8-12, 2013. 458–469.  https://doi.org/10.1109/
## ICDE.2013.6544847
## [11]
## Xu Chu, Mourad Ouzzani, John Morcos, Ihab F. Ilyas, Paolo Papotti, Nan Tang,
and Yin Ye. 2015. KATARA: Reliable Data Cleaning with Knowledge Bases and
Crowdsourcing.Proc. VLDB Endow.8, 12 (2015), 1952–1955.  https://doi.org/10.
## 14778/2824032.2824109
[12]Gao Cong, Wenfei Fan, Floris Geerts, Xibei Jia, and Shuai Ma. 2007. Improving
Data Quality: Consistency and Accuracy. InVLDB’07. 315–326.
[13]Graham Cormode, Lukasz Golab, Flip Korn, Andrew McGregor, Divesh Srivas-
tava, and Xi Zhang. 2009. Estimating the confidence of conditional functional
dependencies. InProceedings of the ACM SIGMOD International Conference on
Management of Data, SIGMOD 2009, Providence, Rhode Island, USA, June 29 - July
2, 2009, Ugur Çetintemel, Stanley B. Zdonik, Donald Kossmann, and Nesime
Tatbul (Eds.). ACM, 469–482.  https://doi.org/10.1145/1559845.1559895
## [14]
## Michele Dallachiesa, Amr Ebaid, Ahmed Eldawy, Ahmed K. Elmagarmid, Ihab F.
Ilyas, Mourad Ouzzani, and Nan Tang. 2013. NADEEF: a commodity data clean-
ing system. InProceedings of the ACM SIGMOD International Conference on
Management of Data, SIGMOD 2013, New York, NY, USA, June 22-27, 2013, Ken-
neth A. Ross, Divesh Srivastava, and Dimitris Papadias (Eds.). ACM, 541–552.
https://doi.org/10.1145/2463676.2465327
## [15]
Sushovan De, Yuheng Hu, Venkata Vamsikrishna Meduri, Yi Chen, and Sub-
barao Kambhampati. 2016.   BayesWipe: A Scalable Probabilistic Framework
for  Improving  Data  Quality.ACM J. Data Inf. Qual.8,  1  (2016),  5:1–5:30.
https://doi.org/10.1145/2992787
[16]Dong Deng, Raul Castro Fernandez, Ziawasch Abedjan, Sibo Wang, Michael
## Stonebraker, Ahmed K. Elmagarmid, Ihab F. Ilyas, Samuel Madden, Mourad Ouz-
zani, and Nan Tang. 2017. The Data Civilizer System. InCIDR 2017, 8th Biennial
Conference on Innovative Data Systems Research, Chaminade, CA, USA, January 8-
11, 2017, Online Proceedings. www.cidrdb.org.  http://cidrdb.org/cidr2017/papers/
p44-deng-cidr17.pdf
## [17]
Wenfei Fan, Floris Geerts, Xibei Jia, and Anastasios Kementsietsidis. 2008. Condi-
tional Functional Dependencies for Capturing Data Inconsistencies.ACM Trans.
Database Syst.33, 2, Article 6 (June 2008), 48 pages.
[18]Floris Geerts, Giansalvatore Mecca, Paolo Papotti, and Donatello Santoro. 2013.
The LLUNATIC Data-cleaning Framework.Proc. VLDB Endow.6, 9 (July 2013),
625–636.   https://doi.org/10.14778/2536360.2536363
## [19]
Lukasz Golab, Howard Karloff, Flip Korn, Divesh Srivastava, and Bei Yu. 2008.
On Generating Near-optimal Tableaux for Conditional Functional Dependencies.
Proc. VLDB Endow.(Aug. 2008).   https://doi.org/10.14778/1453856.1453900
[20]Shuang Hao, Nan Tang, Guoliang Li, Jian He, Na Ta, and Jianhua Feng. 2017. A
Novel Cost-Based Model for Data Repairing.IEEE Trans. on Knowl. and Data Eng.
29, 4 (April 2017), 727–742.   https://doi.org/10.1109/TKDE.2016.2637928
[21]Ihab F. Ilyas and Xu Chu. 2015. Trends in Cleaning Relational Data: Consistency
and Deduplication.Foundations and Trends in Databases5, 4 (2015), 281–393.
https://doi.org/10.1561/1900000045
[22]Matteo Interlandi and Nan Tang. 2015.   Proof positive and negative in data
cleaning. In2015 IEEE 31st International Conference on Data Engineering. IEEE,
## 18–29.
## [23]
Solmaz Kolahi and Laks V. S. Lakshmanan. 2009. On Approximating Optimum
Repairs for Functional Dependency Violations(ICDT ’09).
[24]Mohammad Mahdavi and Ziawasch Abedjan. 2020. Baran: Effective Error Cor-
rection  via  a  Unified  Context  Representation  and  Transfer  Learning.Proc.
VLDB Endow.13, 11 (2020), 1948–1961.  http://www.vldb.org/pvldb/vol13/p1948-
mahdavi.pdf
## [25]
Theodoros Rekatsinas, Xu Chu, Ihab F. Ilyas, and Christopher Ré. 2017. HoloClean:
Holistic Data Repairs with Probabilistic Inference.Proc. VLDB Endow.10, 11 (Aug.
2017), 1190–1201.   https://doi.org/10.14778/3137628.3137631
## [26]
## El Kindi Rezig, Lei Cao, Giovanni Simonini, Maxime Schoemans, Samuel Madden,
Nan Tang, Mourad Ouzzani, and Michael Stonebraker. 2020.  Dagger: A Data
(not code) Debugger. InCIDR 2020, 10th Conference on Innovative Data Systems
## Research, Amsterdam, The Netherlands, January 12-15, 2020, Online Proceedings.
www.cidrdb.org.  http://cidrdb.org/cidr2020/papers/p35-rezig-cidr20.pdf
[27]Jaroslaw Szlichta, Parke Godfrey, Lukasz Golab, Mehdi Kargar, and Divesh Sri-
vastava. 2018. Effective and Complete Discovery of Bidirectional Order Depen-
dencies via Set-based Axioms.The VLDB Journal27, 4 (Aug. 2018), 573–591.
https://doi.org/10.1007/s00778-018-0510-0
## [28]
Robert Tarjan. 1972.   Depth first search and linear graph algorithms.SIAM
## JOURNAL ON COMPUTING1, 2 (1972).
[29]  Manasi Vartak and Samuel Madden. 2018. MODELDB: Opportunities and Chal-
lenges in Managing Machine Learning Models.IEEE Data Eng. Bull.41, 4 (2018),
16–25.  http://sites.computer.org/debull/A18dec/p16.pdf
[30]Jiannan Wang, Sanjay Krishnan, Michael J. Franklin, Ken Goldberg, Tim Kraska,
and Tova Milo. 2014. A sample-and-clean framework for fast and accurate query
processing on dirty data. InInternational Conference on Management of Data,
SIGMOD 2014, Snowbird, UT, USA, June 22-27, 2014, Curtis E. Dyreson, Feifei
Li, and M. Tamer Özsu (Eds.). ACM, 469–480.  https://doi.org/10.1145/2588555.
## 2610505
## [31]
Jiannan Wang and Nan Tang. 2017. Dependable Data Repairing with Fixing Rules.
ACM J. Data Inf. Qual.8, 3-4 (2017), 16:1–16:34.  https://doi.org/10.1145/3041761
[32]Mohamed Yakout, Laure Berti-Équille, and Ahmed K. Elmagarmid. 2013. Don’T
Be SCAREd: Use SCalable Automatic REpairing with Maximal Likelihood and
Bounded Changes(SIGMOD ’13).
## 2554