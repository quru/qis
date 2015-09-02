# QIS on Amazon AWS

When complete, notes on how to install QIS at Amazon (EC2, ECS, EBS, and all
the elastics) will go here.

## Creating the QIS AMI

We use a single AMI with all the QIS components and dependencies pre-installed.
This can then be used as the basis for any architecture on AWS by enabling or
disabling individual services.

* Launch a new Fedora 21 AMI (we used ami-413c5436, Fedora 21 Standard HVM) instance
* Set the default storage size as 5GB
	* This becomes the minimum storage size when launching instances
* Install QIS following the normal instructions in `install.md`, but...
	* Do not enable any of the services (Apache, Memcached, Postgres)
	* Do initialise the empty Postgres cluster and set the standard tuning
	  parameters, but don't create the database
	* Do configure `logrotate`
	* Do raise system limits
	* Do configure SELinux
	* Stop at configuring QIS, and do not run it
	* Run a `yum clean all` and delete any temporary files
* Create a new QIS image from the instance
	* Or the long way round: create a snapshot of the volume, then create
	  a new QIS image from the snapshot
* For further tweaks you can launch a fresh instance from the last-good QIS
  image, make your changes, then create another new image from that

With one or more instances of the AMI created, the script `deploy/aws/configure.sh`
can then be called from e.g. a CloudFormation script to enable and configure the
services required for each server instance.

### AWS regions

AMIs are region-specific, so for example if you create your AMI in the EU (Ireland)
region, it will not be available in the EU (Frankfurt) region. To make your AMI
available elsewhere, select the AMI in the AWS console and choose *Copy AMI* from
the actions menu. You can then select one or more regions to copy the image to.
The copied images will have different IDs.

*Note: if using the AWS CLI, you pull instead of push - first select the
destination region, then copy the image from the source region.*

## Manual deployment

The following steps are required to manually deploy a QIS service on Amazon AWS.
The same steps can be automated in part, using either the AWS command line tools
and/or Amazon's CloudFormation service.

### VPC configuration

Useful reference: [Flux7 Blog](http://blog.flux7.com/blogs/aws/vpc-best-configuration-practices)
TODO This reference advocates creating 6 subnets and separate routing tables.
Does the simpler version below open up too much?

Create a VPC for hosting the QIS server instances:

* `qis-vpc`
	* CIDR block e.g. `192.168.0.0/16`

Go to Subnets and allocate 2 or 3 new Subnets to the VPC,
each in a different availability zone:

* `qis-subnet-1a`
	* VPC `qis-vpc`
	* Availability zone `1a`
	* CIDR block `192.168.0.0/20`
* `qis-subnet-1b`
	* VPC `qis-vpc`
	* Availability zone `1b`
	* CIDR block `192.168.16.0/20`
* `qis-subnet-1c`
	* VPC `qis-vpc`
	* Availability zone `1c`
	* CIDR block `192.168.32.0/20`

Go to Internet Gateways and create a new gateway for the VPC:

* `qis-vpc-ig` 
* Once created, select it and attach to the `qis-vpc` VPC
* Note down its ID e.g. `igw-6b9f4407`

Go to Route Tables and define a route to enable the Subnets to reach the internet
via the new internet gateway:

* Select the *Main* route table for the `qis-vpc` VPC
* On the *Routes* tab, click Edit and add a new route
	* Destination `0.0.0.0/0`, target as the internet gateway ID created above,
	  e.g. `igw-6b9f4407`

### Security groups

Look for the default security group created for the `qis-vpc` VPC, which will
have a group name of `default`. Edit the name tag and set it to `qis-vpc-default-sg`.
Then note down its group ID, e.g. `sg-3fd4fa5b`.

Define the following security groups under the `qis-vpc` VPC:

* `qis-lb-sg` - QIS load balancer
	* Inbound HTTP, source Anywhere `0.0.0.0/0`
	* Inbound HTTPS, source Anywhere `0.0.0.0/0`
	* Outbound ALL, destination as the default VPC security group ID,
	  e.g. `sg-3fd4fa5b`
* `qis-internal-sg` - QIS ports to allow within the VPC
	* Inbound HTTP, source as the default VPC security group ID,
	  e.g. `sg-3fd4fa5b`
	* Inbound HTTPS, source as the default VPC security group ID
	* Inbound SSH, source as the default VPC security group ID
	* Inbound TCP 5432 (Postgres), source as the default VPC security group ID
	* Inbound TCP 11211 (Memcached), source as the default VPC security group ID
	* Outbound ALL, destination as the default VPC security group ID
* `qis-external-ssh-sg` - QIS external SSH access
	* Inbound SSH, source either `0.0.0.0/0` (open to the world) or
	  your external IP address (for better security)

### Load balancer

For the most common architectures (those with multiple web servers, for performance,
reliability, and zero-downtime maintenance) you will need a load balancer.

In the EC2 console, define a new load balancer (ELB) as follows:

* Name `qis-lb`
* Create LB inside the `qis-vpc` VPC
* Leave *internal load balancer* unchecked
* Add HTTP port 80 to HTTP port 80
* Add HTTPS port 443 to HTTP port 80
	* This simplifies the QIS deployment, in that all 'internal' traffic will
	  be plain HTTP, there will be no need for SSL certificates on the individual
	  web servers
* Add all `qis-subnet-*` Subnets from the *available* to the *selected* Subnets list
* Select `qis-lb-sg` as the security group
* Set the SSL details
	* For a temporary self-signed certificate, run commands:  
	  `openssl genrsa -out my-private-key.pem 2048`  
	  `openssl req -sha256 -new -key my-private-key.pem -out csr.pem`  
	  `openssl x509 -req -days 365 -in csr.pem -signkey my-private-key.pem -out my-certificate.pem`
* Set the health check to ping path `/` on HTTP port 80
* Skip the EC2 instances, if the QIS web servers are not yet running
* Skip the tags and create the load balancer

TODO With all traffic on port 80, we need to re-configure the Apache conf files
to disable the port 443 workers and move them to port 80.

### 2 server auto-scaling deployment

This architecture features 1 full-time web server, and 1 full-time database
and image storage server. When the CPU load becomes high on the master web
server, additional web servers are automatically created to share the load,
which are then shut down when the load decreases.

TODO Create a launch configuration
TODO Create a scaling group
TODO Create the db server
TODO Create the web server, link to scaling group
TODO Link load balancer to scaling group

If this architecture proves suitable, convert the full-time servers to
reserved instances to achieve substantial cost savings.

## Elastic container service (ECS)

The file `qis-ecs-task.json` contains a task definition for launching linked
Docker containers for the QIS:

* Memcached service
* Postgres database service
* Postgres data files volume
* Web (application server) service
* Images and web logs data volume

Unfortunately, this task definition does not yet work.

