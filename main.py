#!/usr/bin/env python3

import sys
import json
from collections import OrderedDict

from knack import CLI, ArgumentsContext, CLICommandsLoader
from knack.commands import CommandGroup

from ssdp import SSDP, Router
from upnp import UPnp

class CommandsLoader(CLICommandsLoader):

    def load_command_table(self, args):
        with CommandGroup(self, 'router', '__main__#{}') as g:
            g.command('list', 'router_list')
        with CommandGroup(self, 'port', '__main__#{}') as g:
            g.command('add', 'port_add')
            g.command('delete', 'port_delete')
            g.command('list', 'port_list')
        return OrderedDict(self.command_table)

    def load_arguments(self, command):
        with ArgumentsContext(self, 'router list') as ac:
            ac.argument('refresh', default=False)
        with ArgumentsContext(self, 'port add') as ac:
            ac.argument('router', type=str, help="The router's UUID.")
            ac.argument('protocol', type=str, default='TCP', required=False, help="TCP or UDP.")
            ac.argument('public_port', type=int, default=0, required=False)
            ac.argument('private_ip', type=str)
            ac.argument('private_port', type=int)
        with ArgumentsContext(self, 'port delete') as ac:
            ac.argument('router', type=str, help="The router's UUID.")
            ac.argument('protocol', type=str, default='TCP', required=False, help="TCP or UDP.")
            ac.argument('public_port', type=int, default=0, required=False)
        with ArgumentsContext(self, 'port list') as ac:
            ac.argument('router', type=str, help="The router's UUID.")

        super(CommandsLoader, self).load_arguments(command)

def router_list(refresh=False):
    # print("[router_list] refresh=%s" % refresh)

    routers = SSDP.list(refresh)

    print()
    template = "{0:20}{1:40}{2:50}{3:50}"
    print(template.format("SERVER", "UUID", "TYPE", "URL"))

    for r in routers:
        print(template.format(
            "%s:%d" % (r.ip, r.port),
            r.uuid,
            r.type,
            r.url
        ))

def port_add(router, protocol, public_port, private_ip, private_port):
    if not public_port:
        public_port = private_port

    # print("[port_add] router=%s protocol=%s public_port=%d private_ip=%s private_port=%s" \
    #         % (router, protocol, public_port, private_ip, private_port))
    
    UPnp.add_port_mapping(
        router_uuid=router,
        protocol=protocol,
        public_port=public_port,
        private_ip=private_ip,
        private_port=private_port
    )

def port_delete(router, protocol, public_port):
    # print("[port_delete] router=%s protocol=%s public_port=%d" \
    #         % (router, protocol, public_port))

    UPnp.delete_port_mapping(
        router_uuid=router,
        protocol=protocol,
        public_port=public_port
    )

def port_list(router):
    UPnp.list_port_mappings(router_uuid=router)

def main():
    mycli = CLI(cli_name='upnp', commands_loader_cls=CommandsLoader)
    exit_code = mycli.invoke(sys.argv[1:])

if __name__ == '__main__':
    main()

# Commands needed
# main.py routers list
#
# main.py port list <-- not sure if this is possible
# main.py port add <router> <protocol> <public-port> <private-ip> <private-port>
# main.py port delete <router> <protocol> <public-port>

# print(json.dumps([r.__dict__ for r in routers]))