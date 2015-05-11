#!/bin/bash
#NOTE: MozDef defaults all type: string to index: not_analyzed.

HOST="FILL_ME:9200/"
INDEX="rra"

curl -XPUT ${HOST}${INDEX} -d '{
	"settings": {
		"number_of_shards": 1,
		"number_of_replicas": 1
	}
}'
