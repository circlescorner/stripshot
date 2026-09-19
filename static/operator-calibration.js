'use strict';
const toolPost=(action,data={})=>post('/api/operator-tools/'+action,JSON.stringify(data),true);
