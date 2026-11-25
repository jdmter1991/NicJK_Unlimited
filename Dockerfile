# Builder image
FROM ubuntu:22.04 AS builder

ARG NICJK_REF=unknown
ARG NICJK_COMMIT=unknown

# Install build tools and libraries
RUN dpkg --add-architecture i386 &&\
	apt-get -q update &&\
	DEBIAN_FRONTEND="noninteractive" apt-get -q install -y -o Dpkg::Options::="--force-confnew" --no-install-recommends build-essential gcc-multilib g++-multilib cmake git zlib1g-dev zlib1g-dev:i386 &&\
	rm -rf /var/lib/apt/lists/*

# Copy sources
COPY . /usr/src/nicjk

# Build i386 arch
RUN mkdir /usr/src/nicjk/build.i386 &&\
	cd /usr/src/nicjk/build.i386 &&\
	cmake -DCMAKE_TOOLCHAIN_FILE=cmake/Toolchains/linux-i686.cmake \
		-DCMAKE_INSTALL_PREFIX=/opt \
		-DBuildMPCGame=OFF -DBuildMPEngine=OFF -DBuildMPRdVanilla=OFF -DBuildMPUI=OFF -DBuildMPRend2=OFF -DBuildMPRdVulkan=OFF \
		.. &&\
	cmake --build . -j $(nproc) &&\
	cmake --install .

# Build x86_64 arch
RUN mkdir /usr/src/nicjk/build.x86_64 &&\
	cd /usr/src/nicjk/build.x86_64 &&\
	cmake -DCMAKE_INSTALL_PREFIX=/opt \
		-DBuildMPCGame=OFF -DBuildMPEngine=OFF -DBuildMPRdVanilla=OFF -DBuildMPUI=OFF -DBuildMPRend2=OFF -DBuildMPRdVulkan=OFF \
		.. &&\
	cmake --build . -j $(nproc) &&\
	cmake --install .


# Server image
FROM ubuntu:22.04

ARG NICJK_REF=unknown
ARG NICJK_COMMIT=unknown

LABEL org.opencontainers.image.title="NicJK"
LABEL org.opencontainers.image.description="NicJK dedicated server"
LABEL org.opencontainers.image.licenses="GPL-2.0-only"
LABEL io.tayst.nicjk.upstream.ref="${NICJK_REF}"
LABEL io.tayst.nicjk.upstream.commit="${NICJK_COMMIT}"

# Install utilities and libraries
RUN dpkg --add-architecture i386 &&\
	apt-get -q update &&\
	DEBIAN_FRONTEND="noninteractive" apt-get -q install -y -o Dpkg::Options::="--force-confnew" --no-install-recommends socat libstdc++6 libstdc++6:i386 zlib1g zlib1g:i386 &&\
	rm -rf /var/lib/apt/lists/* &&\
	useradd --create-home --home-dir /home/container --shell /bin/bash container

# Copy binaries and scripts
RUN mkdir -p /opt/nicjk/cdpath/base /opt/nicjk/cdpath/nicjk /opt/nicjk/basepath/nicjk /opt/nicjk/homepath
COPY --from=builder /opt/JediAcademy/nicjkded.* /opt/nicjk/
COPY --from=builder /opt/JediAcademy/nicjk/ /opt/nicjk/cdpath/nicjk/
COPY scripts/docker/*.sh /opt/nicjk/
COPY scripts/docker/*.cfg /opt/nicjk/basepath/nicjk/
RUN chmod +x /opt/nicjk/nicjkded.* /opt/nicjk/*.sh \
    && chown -R container:container /opt/nicjk

# Write metadata
RUN printf '%s\n' "${NICJK_COMMIT}" > /opt/nicjk/.upstream-commit \
	&& printf '%s\n' "${NICJK_REF}" > /opt/nicjk/.upstream-ref

# Execution
ENV TJK_OPTS="+exec server.cfg"
EXPOSE 29070/udp
EXPOSE 18200/tcp
HEALTHCHECK --interval=10s --timeout=9s --retries=6 CMD ["/opt/nicjk/healthcheck.sh"]
USER container
ENV USER=container HOME=/home/container
CMD ["/opt/nicjk/run.sh"]
