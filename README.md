# Introduction

This project adds the following capabilities for UPnP devices.

- List routers
- List UPnP ports on a router
- Add a port mapping
- Delete a port mapping

*This project does not implement the full SSDP and UPnP specifications.*

# Installing

You need to install the [knack command line interface framework](https://github.com/microsoft/knack).

    $ pip3 install --user knack

# Usage

You should use python-3 to run this tool.

## Listing routers

    $ python3 main.py router list

## List ports

    $ python3 main.py port list --router <router-uuid>

## Add port mapping

If not given, the `--public-port` option defaults to the value of `--private-port`, and `--protocol` defaults to `TCP`.

    $ python3 main.py port add --router <router-uuid> --private-ip <private-ip> --private-port <port> --public-port <port> --protocol <TCP|UDP>

## Delete port mapping

    $ python3 main.py port delete --router <router-uuid> --protocol <TCP|UDP> --public-port <port>